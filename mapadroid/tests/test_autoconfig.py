import copy
import json
import unittest
from functools import wraps
from typing import Any
import xml.etree.ElementTree
import mapadroid.tests.test_variables as global_variables
from mapadroid.tests import test_variables
from mapadroid.tests.test_utils import (GetStorage, ResourceCreator,
                                        get_connection_api,
                                        get_connection_mitm)
from mapadroid.utils.autoconfig import AutoConfIssues
from mapadroid.utils.walkerArgs import parse_args


args = parse_args()
email_base: str = "UnitTest@UnitTest.com"
pwd_base: str = "base"
pd_host = 'http://1.1.1.69:8000'
pd_conf = {
    'post_destination': pd_host
}
rgc_host = 'ws://192.168.1.69:8080'
rgc_conf = {
    'websocket_uri': rgc_host
}


def create_valid_configs(test_obj, api_creator, auth: bool = True, pdconf: dict = None, rgcconf: dict = None):
    conf_pd = pdconf if pdconf is not None else pd_conf
    conf_rgc = rgcconf if rgcconf is not None else rgc_conf
    if auth:
        payload = {
            'username': email_base,
            'password': pwd_base
        }
        (auth_shared, _) = api_creator.create_valid_resource('auth', payload=payload)
        conf_pd['mad_auth'] = auth_shared['uri'].split('/')[-1]
        conf_rgc['mad_auth'] = auth_shared['uri'].split('/')[-1]
    res = test_obj.api.post('/api/autoconf/pd', json=conf_pd)
    test_obj.assertTrue(res.status_code == 200)
    res = test_obj.api.post('/api/autoconf/rgc', json=conf_rgc)
    test_obj.assertTrue(res.status_code == 200)


def basic_autoconf(func) -> Any:
    @wraps(func)
    def decorated(self, *args, **kwargs):
        api_creator = ResourceCreator(self.api)
        gacct = None
        session_id = None
        try:
            res = self.mitm.post('/autoconfig/register')
            self.assertTrue(res.status_code == 201)
            session_id = res.content.decode('utf-8')
            # Setup basic PD Auth
            payload = {
                'username': email_base,
                'password': pwd_base
            }
            (auth_shared, _) = api_creator.create_valid_resource('auth', payload=payload)
            auth = {
                'mad_auth': auth_shared['uri'].split('/')[-1]
            }
            res = self.api.post('/api/autoconf/pd', json=auth)
            # Create Google Account
            gacc = {
                "login_type": "google",
                "username": "Unit",
                "password": "Test"
            }
            res = self.api.post('/api/pogoauth', json=gacc)
            gacct = res.headers['X-URI']
            self.assertTrue(res.status_code == 201)
            dev_payload = copy.copy(global_variables.DEFAULT_OBJECTS['device']['payload'])
            dev_payload['account_id'] = gacct
            (dev_info, _) = api_creator.create_valid_resource('device', payload=dev_payload)
            accept_info = {
                'status': 1,
                'device_id': dev_info['uri']
            }
            res = self.api.post('/api/autoconf/{}'.format(session_id), json=accept_info)
            self.assertTrue(res.status_code == 200)
            res = self.mitm.get('/autoconfig/{}/status'.format(session_id))
            self.assertTrue(res.status_code == 200)
            (ss_info, _) = api_creator.create_valid_resource('devicesetting')
            func(self, session_id, dev_info, ss_info, api_creator, *args, **kwargs)
        except Exception:
            raise
        finally:
            api_creator.remove_resources()
            if session_id is not None:
                self.mitm.delete('/autoconfig/{}/complete'.format(session_id))
            if gacct is not None:
                self.api.delete(gacct)
    return decorated


class MITMAutoConf(unittest.TestCase):
    def setUp(self):
        self.api = get_connection_api()
        self.mitm = get_connection_mitm(self.api)

    def tearDown(self):
        self.api.close()
        self.mitm.close()

    def test_no_auth(self):
        # Remove any existing auth
        auths = self.api.get('/api/auth').json()
        for auth_id in auths.keys():
            self.api.delete('/api/auth/{}'.format(auth_id))
        res = self.mitm.get('/autoconfig/0/status')
        self.assertTrue(res.status_code == 404)
        res = self.mitm.post('/autoconfig/register')
        self.assertTrue(res.status_code == 201)
        session_id = res.content.decode('utf-8')
        res = self.mitm.delete('/autoconfig/{}/complete'.format(session_id))
        self.assertTrue(res.status_code == 200)

    def test_workflow_assigned_device(self):
        api_creator = ResourceCreator(self.api)
        gacct = None
        session_id = None
        try:
            res = self.mitm.post('/autoconfig/register')
            self.assertTrue(res.status_code == 201)
            session_id = res.content.decode('utf-8')
            res = self.mitm.get('/autoconfig/{}/status'.format(session_id))
            self.assertTrue(res.status_code == 406)
            # Create Google Account
            gacc = {
                "login_type": "google",
                "username": "Unit",
                "password": "Test"
            }
            res = self.api.post('/api/pogoauth', json=gacc)
            gacct = res.headers['X-URI']
            self.assertTrue(res.status_code == 201)
            dev_payload = copy.copy(global_variables.DEFAULT_OBJECTS['device']['payload'])
            dev_payload['account_id'] = gacct
            (dev_info, _) = api_creator.create_valid_resource('device', payload=dev_payload)
            accept_info = {
                'status': 1,
                'device_id': dev_info['uri']
            }
            res = self.api.post('/api/autoconf/{}'.format(session_id), json=accept_info)
            self.assertTrue(res.status_code == 200)
            res = self.mitm.get('/autoconfig/{}/status'.format(session_id))
            self.assertTrue(res.status_code == 200)
            data = '2,UnitTest Log Message'
            res = self.mitm.post('/autoconfig/{}/log'.format(session_id), data=data)
            self.assertTrue(res.status_code == 201)
            res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
            self.assertTrue(res.status_code == 200)
            res = self.mitm.get('/autoconfig/{}/rgc'.format(session_id))
            self.assertTrue(res.status_code == 200)
            res = self.mitm.get('/autoconfig/{}/google'.format(session_id))
            self.assertTrue(res.status_code == 200)
            self.assertTrue(res.content == b'Unit\nTest')
            res = self.mitm.delete('/autoconfig/{}/complete'.format(session_id))
            self.assertTrue(res.status_code == 200)
        except Exception:
            raise
        finally:
            api_creator.remove_resources()
            if session_id is not None:
                self.mitm.delete('/autoconfig/{}/complete'.format(session_id))
            if gacct is not None:
                self.api.delete(gacct)

    def test_no_configured_endpoints(self):
        api_creator = ResourceCreator(self.api)
        session_id = None
        try:
            res = self.mitm.post('/autoconfig/register')
            self.assertTrue(res.status_code == 201)
            session_id = res.content.decode('utf-8')
            (dev_info, _) = api_creator.create_valid_resource('device')
            accept_info = {
                'status': 1,
                'device_id': dev_info['uri']
            }
            with GetStorage(self.api) as storage:
                storage.upload_all()
                res = self.api.post('/api/autoconf/{}'.format(session_id), json=accept_info)
                self.assertTrue(res.status_code == 406)
                expected_issues = {
                    'X-Critical': [
                        AutoConfIssues.pd_not_configured.value,
                        AutoConfIssues.rgc_not_configured.value,
                    ],
                    'X-Warnings': [
                        AutoConfIssues.no_ggl_login.value,
                        AutoConfIssues.auth_not_configured.value,
                    ]
                }
                self.assertListEqual(expected_issues['X-Critical'], json.loads(res.headers['X-Critical']))
                self.assertListEqual(expected_issues['X-Warnings'], json.loads(res.headers['X-Warnings']))
        finally:
            api_creator.remove_resources()
            if session_id is not None:
                self.mitm.delete('/autoconfig/{}/complete'.format(session_id))

    @basic_autoconf
    def test_pd_token_override(self, session_id, dev_info, ss_info, api_creator):
        pwd_sharedsettings: str = "sharedsettings"
        pwd_device: str = "device"
        # Test basic config
        res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
        self.assertTrue(res.status_code == 200)
        root = xml.etree.ElementTree.fromstring(res.content)
        username = root.find(".//*[@name='user_id']").text
        pwd = root.find(".//*[@name='auth_token']").text
        self.assertTrue(username == email_base)
        self.assertTrue(pwd == pwd_base)
        # Test Shared Setting Config
        update_info = {
            'pool': ss_info['uri']
        }
        res = self.api.patch(dev_info['uri'], json=update_info)
        self.assertTrue(res.status_code == 204)
        update_info = {
            'pd_token_override': pwd_sharedsettings
        }
        res = self.api.patch(dev_info['uri'], json=update_info)
        self.assertTrue(res.status_code == 204)
        res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
        self.assertTrue(res.status_code == 200)
        root = xml.etree.ElementTree.fromstring(res.content)
        username = root.find(".//*[@name='user_id']").text
        pwd = root.find(".//*[@name='auth_token']").text
        self.assertTrue(username == email_base)
        self.assertTrue(pwd == pwd_sharedsettings)
        # Test Device Config
        update_info = {
            'pd_token_override': pwd_device
        }
        res = self.api.patch(dev_info['uri'], json=update_info)
        self.assertTrue(res.status_code == 204)
        res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
        self.assertTrue(res.status_code == 200)
        root = xml.etree.ElementTree.fromstring(res.content)
        username = root.find(".//*[@name='user_id']").text
        pwd = root.find(".//*[@name='auth_token']").text
        self.assertTrue(username == email_base)
        self.assertTrue(pwd == pwd_device)
        res = self.mitm.delete('/autoconfig/{}/complete'.format(session_id))
        self.assertTrue(res.status_code == 200)

    @basic_autoconf
    def test_basic_auth_override(self, session_id, dev_info, ss_info, api_creator):
        elem_shared: str = "sharedsettings"
        elem_dev: str = "device"
        payload = {
            'username': elem_shared,
            'password': elem_shared
        }
        (auth_shared, _) = api_creator.create_valid_resource('auth', payload=payload)
        payload = {
            'username': elem_dev,
            'password': elem_dev
        }
        (auth_dev, _) = api_creator.create_valid_resource('auth', payload=payload)
        # Test basic config
        res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
        self.assertTrue(res.status_code == 200)
        root = xml.etree.ElementTree.fromstring(res.content)
        username = root.find(".//*[@name='auth_username']").text
        pwd = root.find(".//*[@name='auth_password']").text
        self.assertTrue(username == email_base)
        self.assertTrue(pwd == pwd_base)
        # Test Shared Setting Config
        update_info = {
            'pool': ss_info['uri']
        }
        res = self.api.patch(dev_info['uri'], json=update_info)
        self.assertTrue(res.status_code == 204)
        update_info = {
            'basic_auth_override': auth_shared['uri']
        }
        res = self.api.patch(ss_info['uri'], json=update_info)
        self.assertTrue(res.status_code == 204)
        res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
        self.assertTrue(res.status_code == 200)
        root = xml.etree.ElementTree.fromstring(res.content)
        username = root.find(".//*[@name='auth_username']").text
        pwd = root.find(".//*[@name='auth_password']").text
        self.assertTrue(username == elem_shared)
        self.assertTrue(pwd == elem_shared)
        # Test Device Config
        update_info = {
            'basic_auth_override': auth_dev['uri']
        }
        res = self.api.patch(dev_info['uri'], json=update_info)
        self.assertTrue(res.status_code == 204)
        res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
        self.assertTrue(res.status_code == 200)
        root = xml.etree.ElementTree.fromstring(res.content)
        username = root.find(".//*[@name='auth_username']").text
        pwd = root.find(".//*[@name='auth_password']").text
        self.assertTrue(username == elem_dev)
        self.assertTrue(pwd == elem_dev)
        res = self.mitm.delete('/autoconfig/{}/complete'.format(session_id))
        self.assertTrue(res.status_code == 200)

    def test_missing_apks(self):
        api_creator = ResourceCreator(self.api)
        session_id = None
        try:
            res = self.mitm.post('/autoconfig/register')
            self.assertTrue(res.status_code == 201)
            session_id = res.content.decode('utf-8')
            (dev_info, _) = api_creator.create_valid_resource('device')
            accept_info = {
                'status': 1,
                'device_id': dev_info['uri']
            }
            with GetStorage(self.api) as storage:
                res = self.api.post('/api/autoconf/{}'.format(session_id), json=accept_info)
                self.assertTrue(res.status_code == 406)
                expected_issues = {
                    'X-Critical': [
                        AutoConfIssues.pd_not_configured.value,
                        AutoConfIssues.rgc_not_configured.value,
                        AutoConfIssues.package_missing.value,
                    ],
                    'X-Warnings': [
                        AutoConfIssues.no_ggl_login.value,
                        AutoConfIssues.auth_not_configured.value,
                    ]
                }
                self.assertListEqual(expected_issues['X-Critical'], json.loads(res.headers['X-Critical']))
                self.assertListEqual(expected_issues['X-Warnings'], json.loads(res.headers['X-Warnings']))
                storage.upload_rgc()
                res = self.api.post('/api/autoconf/{}'.format(session_id), json=accept_info)
                self.assertTrue(res.status_code == 406)
                expected_issues = {
                    'X-Critical': [
                        AutoConfIssues.pd_not_configured.value,
                        AutoConfIssues.rgc_not_configured.value,
                        AutoConfIssues.package_missing.value,
                    ],
                    'X-Warnings': [
                        AutoConfIssues.no_ggl_login.value,
                        AutoConfIssues.auth_not_configured.value,
                    ]
                }
                self.assertListEqual(expected_issues['X-Critical'], json.loads(res.headers['X-Critical']))
                self.assertListEqual(expected_issues['X-Warnings'], json.loads(res.headers['X-Warnings']))
                storage.upload_pd()
                res = self.api.post('/api/autoconf/{}'.format(session_id), json=accept_info)
                self.assertTrue(res.status_code == 406)
                expected_issues = {
                    'X-Critical': [
                        AutoConfIssues.pd_not_configured.value,
                        AutoConfIssues.rgc_not_configured.value,
                        AutoConfIssues.package_missing.value,
                    ],
                    'X-Warnings': [
                        AutoConfIssues.no_ggl_login.value,
                        AutoConfIssues.auth_not_configured.value,
                    ]
                }
                self.assertListEqual(expected_issues['X-Critical'], json.loads(res.headers['X-Critical']))
                self.assertListEqual(expected_issues['X-Warnings'], json.loads(res.headers['X-Warnings']))
                storage.upload_pogo()
                res = self.api.post('/api/autoconf/{}'.format(session_id), json=accept_info)
                self.assertTrue(res.status_code == 406)
                expected_issues = {
                    'X-Critical': [
                        AutoConfIssues.pd_not_configured.value,
                        AutoConfIssues.rgc_not_configured.value,
                    ],
                    'X-Warnings': [
                        AutoConfIssues.no_ggl_login.value,
                        AutoConfIssues.auth_not_configured.value,
                    ]
                }
                self.assertListEqual(expected_issues['X-Critical'], json.loads(res.headers['X-Critical']))
                self.assertListEqual(expected_issues['X-Warnings'], json.loads(res.headers['X-Warnings']))
        finally:
            api_creator.remove_resources()
            if session_id is not None:
                self.mitm.delete('/autoconfig/{}/complete'.format(session_id))

    def test_autoconfig_file_download(self):
        api_creator = ResourceCreator(self.api)
        with GetStorage(self.api) as storage:
            try:
                # this really isnt an api call but whatever
                res = self.api.get('/autoconfig/download')
                self.assertTrue(res.status_code == 406)
                # Setup default env without anything defined
                create_valid_configs(self, api_creator, auth=False)
                storage.upload_all()
                res = self.api.get('/autoconfig/download')
                self.assertTrue(res.status_code == 200)
                self.assertTrue(pd_host == res.content.decode('utf-8'))
                create_valid_configs(self, api_creator)
                res = self.api.get('/autoconfig/download')
                self.assertTrue(res.status_code == 200)
                auth = f"{email_base}:{pwd_base}"
                expected = f"{pd_host}\n{auth}"
                self.assertTrue(expected == res.content.decode('utf-8'))
            except Exception:
                raise
            finally:
                rgc_delete = self.api.delete('/api/autoconf/rgc')
                pd_delete = self.api.delete('/api/autoconf/pd')
                api_creator.remove_resources()
                self.assertTrue(rgc_delete.status_code == 200)
                self.assertTrue(pd_delete.status_code == 200)

    @basic_autoconf
    def test_workflow_assigned_device(self, session_id, dev_info, ss_info, api_creator):
        res = self.mitm.get('/autoconfig/{}/status'.format(session_id))
        self.assertTrue(res.status_code == 200)
        data = '2,UnitTest Log Message'
        res = self.mitm.post('/autoconfig/{}/log'.format(session_id), data=data)
        self.assertTrue(res.status_code == 201)
        res = self.mitm.get('/autoconfig/{}/pd'.format(session_id))
        self.assertTrue(res.status_code == 200)
        res = self.mitm.get('/autoconfig/{}/rgc'.format(session_id))
        self.assertTrue(res.status_code == 200)
        res = self.mitm.get('/autoconfig/{}/google'.format(session_id))
        self.assertTrue(res.status_code == 200)
        self.assertTrue(res.content == b'unit\nTest')
        res = self.mitm.delete('/autoconfig/{}/complete'.format(session_id))
        self.assertTrue(res.status_code == 200)

    @unittest.skip("PD emails are case sensitive")
    def test_lower_case(self):
        api_creator = ResourceCreator(self.api)
        with GetStorage(self.api):
            try:
                pd_email = 'UPPERcase'
                pd_update = {
                    'user_id': pd_email
                }
                create_valid_configs(self, api_creator)
                res = self.api.patch('/api/autoconf/pd', json=pd_update)
                self.assertTrue(res.status_code == 200)
                res = self.api.get('/api/autoconf/pd')
                self.assertTrue(res.status_code == 200)
                self.assertTrue(res.json()['user_id'] == pd_email.lower())
            except Exception:
                raise
            finally:
                self.api.delete('/api/autoconf/rgc')
                self.api.delete('/api/autoconf/pd')
                api_creator.remove_resources()

    def test_duplicate_mac_update(self):
        api_creator = ResourceCreator(self.api)
        payload = copy.copy(test_variables.DEFAULT_OBJECTS['device']['payload'])
        payload['mac_address'] = '00:1F:F3:00:1F:F3'
        api_creator.create_valid_resource('device', payload=payload)
        (dev_update, _) = api_creator.create_valid_resource('device')
        dev_info = self.api.get(dev_update['uri']).json()
        headers = {
            'Origin': dev_info['origin']
        }
        res = self.mitm.post('/autoconfig/mymac', headers=headers, data=payload['mac_address'])
        self.assertTrue(res.status_code == 422)
