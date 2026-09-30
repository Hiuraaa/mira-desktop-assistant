import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from mira.learning import LearningStore
from mira.storage import ConversationStore, MemoryStore
from mira.studio import COOKIE, DesktopStudio, StudioServer


class StudioSecurityTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def dispatch(operation, data):
            self.calls.append((operation, data))
            return {"operation": operation}
        self.server = StudioServer(dispatch)
        self.server.start()

    def tearDown(self):
        self.server.stop()

    def request(self, method, path, data=None, *, host=None, origin=True, cookie=False, csrf=False,
                raw=None, content_type="application/json"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server.server_port, timeout=3)
        headers = {"Host":host or self.server.host}
        if origin:
            headers["Origin"] = self.server.origin if origin is True else origin
        if cookie:
            headers["Cookie"] = f"{COOKIE}={self.server.session}"
        if csrf:
            headers["X-Mira-CSRF"] = self.server.csrf
        if data is not None or raw is not None:
            headers["Content-Type"] = content_type
        payload = raw if raw is not None else json.dumps(data) if data is not None else None
        connection.request(method,path,body=payload,headers=headers)
        response = connection.getresponse()
        result = (response.status,dict(response.getheaders()),response.read())
        connection.close()
        return result

    def test_static_shell_has_csp_and_contains_no_session_token(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn(self.server.token.encode(), body)
        self.assertEqual(self.server.server.server_address[0], "127.0.0.1")

    def test_host_origin_auth_and_csrf_are_all_required_for_mutations(self):
        command = {"operation":"memory_add","data":{"text":"test"}}
        for kwargs in ({}, {"cookie":True}, {"csrf":True},
                       {"cookie":True,"csrf":True,"origin":False},
                       {"cookie":True,"csrf":True,"origin":"https://evil.example"},
                       {"cookie":True,"csrf":True,"host":"evil.example"}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.request("POST","/api/command",command,**kwargs)[0],403)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.request("POST","/api/command",command,cookie=True,csrf=True)[0],200)
        self.assertEqual(self.calls,[('memory_add',{'text':'test'})])

    def test_bootstrap_and_refresh_use_http_only_same_site_cookie(self):
        self.assertEqual(self.request("POST","/api/session",{"token":"wrong"})[0],401)
        status,headers,body = self.request("POST","/api/session",{"token":self.server.token})
        self.assertEqual(status,200)
        self.assertIn("HttpOnly",headers["Set-Cookie"])
        self.assertIn("SameSite=Strict",headers["Set-Cookie"])
        self.assertEqual(json.loads(body)["csrf"], self.server.csrf)
        self.assertEqual(self.request("POST","/api/session",{},cookie=True)[0],200)

    def test_history_and_avatar_require_auth_and_paths_are_allowlisted(self):
        for path in ("/api/state", "/api/avatar"):
            self.assertEqual(self.request("GET",path)[0],401)
        self.assertEqual(self.request("GET","/api/state",cookie=True)[0],200)
        self.assertEqual(self.request("GET","/../storage.py",cookie=True)[0],404)
        self.assertEqual(self.request("GET","/settings.json",cookie=True)[0],404)

    def test_malformed_non_json_and_oversized_requests_do_not_dispatch(self):
        self.assertEqual(self.request("POST","/api/command",raw="not json",cookie=True,csrf=True)[0],400)
        self.assertEqual(self.request("POST","/api/command",raw="[]",cookie=True,csrf=True)[0],400)
        self.assertEqual(self.request("POST","/api/command",raw="{}",content_type="text/plain",cookie=True,csrf=True)[0],415)
        self.assertEqual(self.request("POST","/api/command",raw="x" * 150001,cookie=True,csrf=True)[0],400)
        self.assertEqual(self.calls,[])


class StudioBridgeTests(unittest.TestCase):
    def test_worker_dispatch_waits_for_main_thread_and_unknown_tools_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(path=Path(directory), closed=False, after=lambda *_args:None)
            bridge = DesktopStudio(app)
            output = []
            bridge.handle = lambda operation,data: (threading.get_ident(),operation,data)
            worker = threading.Thread(target=lambda:output.append(bridge.dispatch("test",{"x":1})))
            worker.start()
            # Wait for the queue item without sleeping and execute it on this thread.
            pending = bridge.requests.get(timeout=3)
            bridge.requests.put(pending)
            main_thread = threading.get_ident()
            bridge._pump()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(output,[(main_thread,"test",{"x":1})])
            bridge.stop()

    def test_stopped_bridge_cannot_mutate_store(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(path=Path(directory))
            bridge = DesktopStudio(app)
            bridge.stop()
            with self.assertRaises(RuntimeError):
                bridge.dispatch("memory_add",{"text":"late"})

    def test_busy_chat_cannot_change_active_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = SimpleNamespace(path=root,busy=True,learning=LearningStore(root/"learning.json"))
            bridge = DesktopStudio(app)
            for operation in ("send","chat_new","settings","study_now"):
                with self.subTest(operation=operation), self.assertRaises(ValueError):
                    bridge.handle(operation,{"text":"test"})
            bridge.stop()


if __name__ == "__main__":
    unittest.main()
