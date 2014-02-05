# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013, Nachi Ueno, NTT I3, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock


# from neutron import context
from neutron import context
from neutron.db import api as dbapi
from neutron.openstack.common import uuidutils
from neutron.services.vpn.service_drivers import cisco_csr_db as csr_db
from neutron.services.vpn.service_drivers import cisco_ipsec as ipsec_driver
from neutron.tests import base

_uuid = uuidutils.generate_uuid

FAKE_ROUTER_ID = _uuid()
FAKE_VPN_CONN_ID = _uuid()

FAKE_VPN_CONNECTION = {
    'vpnservice_id': _uuid(),
    'id': FAKE_VPN_CONN_ID,
}
FAKE_VPN_SERVICE = {
    'router_id': FAKE_ROUTER_ID,
    'provider': 'fake_provider'
}
FAKE_HOST = 'fake_host'


class TestCiscoIPsecDriverValidation(base.BaseTestCase):

    def setUp(self):
        super(TestCiscoIPsecDriverValidation, self).setUp()
        self.addCleanup(mock.patch.stopall)
        dbapi.configure_db()
        self.addCleanup(dbapi.clear_db)
        mock.patch('neutron.openstack.common.rpc.create_connection').start()
        self.service_plugin = mock.Mock()
        self.driver = ipsec_driver.CiscoCsrIPsecVPNDriver(self.service_plugin)
        self.context = context.Context('some_user', 'some_tenant')
        self.session = self.context.session
        self.vpn_service = mock.Mock()

    def test_ike_version_unsupported(self):
        """Failure test that Cisco CSR REST API does not support IKE v2."""
        policy_info = {'ike_version': 'v2',
                       'lifetime': {'units': 'seconds', 'value': 60}}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_ike_version, policy_info)

    def test_ike_lifetime_not_in_seconds(self):
        """Failure test of unsupported lifetime units for IKE policy."""
        policy_info = {'lifetime': {'units': 'kilobytes', 'value': 1000}}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_lifetime,
                          "IKE Policy", policy_info)

    def test_ipsec_lifetime_not_in_seconds(self):
        """Failure test of unsupported lifetime units for IPSec policy."""
        policy_info = {'lifetime': {'units': 'kilobytes', 'value': 1000}}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_lifetime,
                          "IPSec Policy", policy_info)

    def test_ike_lifetime_seconds_values_at_limits(self):
        """Test valid lifetime values for IKE policy."""
        policy_info = {'lifetime': {'units': 'seconds', 'value': 60}}
        self.assertEqual(60, self.driver.get_lifetime('IKE Policy',
                                                      policy_info))
        policy_info = {'lifetime': {'units': 'seconds', 'value': 86400}}
        self.assertEqual(86400, self.driver.get_lifetime('IKE Policy',
                                                         policy_info))

    def test_ipsec_lifetime_seconds_values_at_limits(self):
        """Test valid lifetime values for IPSec policy."""
        policy_info = {'lifetime': {'units': 'seconds', 'value': 120}}
        self.assertEqual(120, self.driver.get_lifetime('IPSec Policy',
                                                       policy_info))
        policy_info = {'lifetime': {'units': 'seconds', 'value': 2592000}}
        self.assertEqual(2592000, self.driver.get_lifetime('IPSec Policy',
                                                           policy_info))

    def test_ike_lifetime_values_invalid(self):
        """Failure test of unsupported lifetime values for IKE policy."""
        which = "IKE Policy"
        policy_info = {'lifetime': {'units': 'seconds', 'value': 59}}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_lifetime,
                          which, policy_info)
        policy_info = {'lifetime': {'units': 'seconds', 'value': 86401}}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_lifetime,
                          which, policy_info)

    def test_ipsec_lifetime_values_invalid(self):
        """Failure test of unsupported lifetime values for IPSec policy."""
        which = "IPSec Policy"
        policy_info = {'lifetime': {'units': 'seconds', 'value': 119}}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_lifetime,
                          which, policy_info)
        policy_info = {'lifetime': {'units': 'seconds', 'value': 2592001}}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_lifetime,
                          which, policy_info)

    def test_ipsec_connection_with_mtu_at_limits(self):
        """Test IPSec site-to-site connection with MTU at limits."""
        conn_info = {'mtu': 1500}
        self.assertEqual(1500, self.driver.get_mtu(conn_info))
        conn_info = {'mtu': 9192}
        self.assertEqual(9192, self.driver.get_mtu(conn_info))

    def test_ipsec_connection_with_invalid_mtu(self):
        """Failure test of IPSec site connection with unsupported MTUs."""
        conn_info = {'mtu': 1499}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_mtu, conn_info)
        conn_info = {'mtu': 9193}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_mtu, conn_info)

    def test_identifying_next_tunnel_id(self):
        """Make sure available tunnel IDs can be reserved.
        
        Check before adding five entries, and then check for the next
        available, afterwards. Finally, remove one in the middle and
        ensure that it is the next available ID.
        """
        with self.session.begin():
            for i in xrange(5):
                tunnel = csr_db.get_next_available_tunnel_id(self.session)
                self.assertEqual(i, tunnel)
                conn_id = i * 10
                entry = csr_db.IdentifierMap(tenant_id='1',
                                             ipsec_site_conn_id='%d' % conn_id,
                                             ipsec_tunnel_id=tunnel,
                                             ike_policy_id=100)
                self.session.add(entry)
            tunnel = csr_db.get_next_available_tunnel_id(self.session)
            self.assertEqual(5, tunnel)
            # Remove the 3rd entry and verify that this is the next available
            sess_qry = self.session.query(csr_db.IdentifierMap)
            sess_qry.filter_by(ipsec_site_conn_id='20').delete()
            tunnel = csr_db.get_next_available_tunnel_id(self.session)
            self.assertEqual(2, tunnel)

    def test_no_more_tunnel_ids_available(self):
        """Failure test of trying to reserve tunnel, when none available."""
        fake_session = mock.Mock()
        all_tunnels_in_use = [(i,) for i in range(csr_db.MAX_CSR_TUNNELS)]
        fake_session.query.return_value = all_tunnels_in_use
        self.assertRaises(IndexError,
                          csr_db.get_next_available_tunnel_id, fake_session)

    def test_identifying_next_ike_policy_id(self):
        """Make sure available Cisco CSR IKE policy IDs can be reserved.
        
        Check before adding five entries, and then check for the next
        available, afterwards. Finally, remove one in the middle and
        ensure that it is the next available ID. Note: the IKE policy IDs
        are one based.
        """
        with self.session.begin():
            for i in xrange(1,6):
                ike_id = csr_db.get_next_available_ike_policy_id(self.session)
                self.assertEqual(i, ike_id)
                conn_id = i * 10
                entry = csr_db.IdentifierMap(tenant_id='1',
                                             ipsec_site_conn_id='%d' % conn_id,
                                             ipsec_tunnel_id=i,
                                             ike_policy_id=ike_id)
                self.session.add(entry)
            ike_id = csr_db.get_next_available_ike_policy_id(self.session)
            self.assertEqual(6, ike_id)
            # Remove the 3rd entry and verify that this is the next available
            sess_qry = self.session.query(csr_db.IdentifierMap)
            sess_qry.filter_by(ipsec_site_conn_id='30').delete()
            ike_id = csr_db.get_next_available_ike_policy_id(self.session)
            self.assertEqual(3, ike_id)

    def test_no_more_ike_policy_ids_available(self):
        """Failure test of trying to reserve IKE policy ID, when none avail."""
        fake_session = mock.Mock()
        all_in_use = [(i,) for i in range(1, csr_db.MAX_CSR_IKE_POLICIES + 1)]
        fake_session.query.return_value = all_in_use
        self.assertRaises(IndexError,
                          csr_db.get_next_available_ike_policy_id,
                          fake_session)


    def simulate_existing_mappings(self, session):
        """Helper - create three mapping table entries.
        
        Each entry will have the same tenant ID. The IPSec site connection
        will be 10, 20, 30. The mapped tunnel ID will be 1, 2, 3. The
        mapped IKE policy ID will be 1, 2, 3.
        """
        for i in xrange(1, 3):
            conn_id = i * 10
            entry = csr_db.IdentifierMap(tenant_id='1',
                                         ipsec_site_conn_id='%d' % conn_id,
                                         ipsec_tunnel_id=i, 
                                         ike_policy_id=i)
            self.session.add(entry)

    def test_get_ike_policy_id_already_in_use(self):
        """Obtain Cisco CSR IKE policy ID from existing mappings.
         
        Find the Cisco CSR IKE policy ID for another connection that uses
        the same IKE policy. Mocking out find_connection_using_ike_policy()
        as it is just a database lookup.
        """
        with self.session.begin():
            self.simulate_existing_mappings(self.session)
            csr_db.find_connection_using_ike_policy = mock.Mock()
            csr_db.find_connection_using_ike_policy.return_value='20'
            ike_id = csr_db.determine_csr_ike_policy_id('ike-uuid',
                                                        self.session)
            self.assertEqual(2, ike_id)
        
    def test_getting_new_ike_policy_id(self):
        """Reserve new Cisco CSR IKE policy ID from mapping table.
        
        Simulate that an existing connection is not using the IKE policy,
        by mocking out find_connection_using_ike_policy() database lookup,
        and ensure that a new policy ID is choosen.
        """
        pass

    def test_getting_available_ike_policy_id_from_middle(self):
        """Get next available IKE policy ID, after it is no longer in use."""
        pass

#     def test_create_tunnel_mapping(self):
#          conn_info = {'ikepolicy_id': '10',
#                       'id': '100',
#                       'tenant_id': '1000'}
#          tunnel_id, ike_id = csr_db.create_tunnel_mapping(self.context,
#                                                           conn_info)
#          self.assertEqual(0, tunnel_id)
#          self.assertEqual(1, ike_id)
#          conn_info = {'ikepolicy_id': '10',
#                       'id': '101',
#                       'tenant_id': '1000'}
#          tunnel_id, ike_id = csr_db.create_tunnel_mapping(self.context,
#                                                           conn_info)
#          self.assertEqual(1, tunnel_id)
#          self.assertEqual(2, ike_id)

    def simulate_gw_ip_available(self):
        """Helper function indicating that tunnel has a gateway IP."""
        def have_one(self):
            return 1
        self.vpn_service.router.gw_port.fixed_ips.__len__ = have_one
        ip_addr_mock = mock.Mock()
        ip_addr_mock.ip_address = "192.168.200.1"
        self.vpn_service.router.gw_port.fixed_ips = [ip_addr_mock]

    def test_ipsec_connection_with_gateway_ip(self):
        """Test of IPSec connection with gateway IP."""
        # self.session.query.side_effect = []
        self.simulate_gw_ip_available()
        conn_info = {'ikepolicy_id': '9cdb3452-fb6e-4736-9745-3dc8a40e7963',
                     'id': 'c7bea7a0-772e-41fd-9b63-2ac0d19adc47',
                     'tenant_id': '12345'}
        expected = {'site_conn_id': u'Tunnel0',
                    'ike_policy_id': u'1',
                    'ipsec_policy_id': u'9cdb3452fb6e473697453dc8a40e796',
                    'router_public_ip': '192.168.200.1'}
        self.assertEqual(
            expected,
            self.driver.get_cisco_connection_info(self.context,
                                                  conn_info,
                                                  self.vpn_service))

#     def test_tunnel_id_for_multiple_ipsec_connections(self):
#         """Create several IPSec connections to verify tunnel ID is correct.
# 
#         On a fresh startup, tunnel ID reservations start at zero.
#         """
#         self.simulate_gw_ip_available()
#         for i in xrange(5):
#             conn_info = {
#                 'ikepolicy_id': '9cdb3452-fb6e-4736-9745-3dc8a40e7963',
#                 'id': i * 100,
#                 'tenant_id': '12345'
#             }
#             expected = {'site_conn_id': u'Tunnel%d' % i,
#                         'ike_policy_id': u'%d' % (i+1),
#                         'ipsec_policy_id': u'9cdb3452fb6e473697453dc8a40e796',
#                         'router_public_ip': '192.168.200.1'}
#             self.assertEqual(
#                 expected,
#                 self.driver.get_cisco_connection_info(self.context,
#                                                       conn_info,
#                                                       self.vpn_service),
#                 "Matching expected cisco info for entry %d" % i)

    def test_ipsec_connection_with_missing_gateway_ip(self):
        """Failure test of IPSec connection with missing gateway IP."""
        self.vpn_service.router.gw_port = None
        conn_info = {'ikepolicy_id': '9cdb3452-fb6e-4736-9745-3dc8a40e7963',
                     'id': 'c7bea7a0-772e-41fd-9b63-2ac0d19adc47',
                     'tenant_id': '12345'}
        self.assertRaises(ipsec_driver.CsrValidationFailure,
                          self.driver.get_cisco_connection_info,
                          self.context, conn_info, self.vpn_service)


class TestCiscoIPsecDriver(base.BaseTestCase):
    def setUp(self):
        super(TestCiscoIPsecDriver, self).setUp()
        self.addCleanup(mock.patch.stopall)
        dbapi.configure_db()
        self.addCleanup(dbapi.clear_db)
        mock.patch('neutron.openstack.common.rpc.create_connection').start()
        l3_agent = mock.Mock()
        l3_agent.host = FAKE_HOST
        plugin = mock.Mock()
        plugin.get_l3_agents_hosting_routers.return_value = [l3_agent]
        plugin_p = mock.patch('neutron.manager.NeutronManager.get_plugin')
        get_plugin = plugin_p.start()
        get_plugin.return_value = plugin

        self.service_plugin = mock.Mock()
        self.service_plugin.get_l3_agents_hosting_routers.return_value = (
            [l3_agent])
        self.service_plugin._get_vpnservice.return_value = {
            'router_id': FAKE_ROUTER_ID,
            'provider': 'fake_provider'
        }
        self.driver = ipsec_driver.CiscoCsrIPsecVPNDriver(self.service_plugin)

    def test_create_ipsec_site_connection(self):
        pass
        # ctxt = context.Context('', 'somebody')
# TODO(pcm) complete... need to setup site_conn fields
#         with mock.patch.object(self.driver.agent_rpc, 'cast') as cast:
#             self.driver.create_ipsec_site_connection(
#                 ctxt, FAKE_VPN_CONNECTION)
#             cast.assert_called_once_with(
#                 ctxt,
#                 {'args': {'conn_id': FAKE_VPN_CONN_ID},
#                  'namespace': None,
#                  'method': 'create_ipsec_site_connection'},
#                 version='1.0',
#                 topic='cisco_csr_ipsec_agent.fake_host')


#     def test_create_ipsec_site_connection(self):
#         self._test_update(self.driver.create_ipsec_site_connection,
#                           [FAKE_VPN_CONNECTION],
#                           method_name='create_ipsec_site_connection')
#
#     def test_update_ipsec_site_connection(self):
#         self._test_update(self.driver.update_ipsec_site_connection,
#                           [FAKE_VPN_CONNECTION, FAKE_VPN_CONNECTION],
#                           method_name='update_ipsec_site_connection')
#
#     def test_delete_ipsec_site_connection(self):
#         self._test_update(self.driver.delete_ipsec_site_connection,
#                           [FAKE_VPN_CONNECTION],
#                           method_name='delete_ipsec_site_connection')
#
#     def test_update_vpnservice(self):
#         self._test_update(self.driver.update_vpnservice,
#                           [FAKE_VPN_SERVICE, FAKE_VPN_SERVICE],
#                           method_name='update_vpnservice')
#
#     def test_delete_vpnservice(self):
#         self._test_update(self.driver.delete_vpnservice,
#                           [FAKE_VPN_SERVICE],
#                           method_name='delete_vpnservice')
