import demistomock as demisto
from CommonServerPython import *
from CommonServerUserPython import *

import urllib3
import traceback
from typing import Dict

# Disable insecure warnings
urllib3.disable_warnings()

''' CONSTANTS '''

DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
MAX_INCIDENTS_TO_FETCH = 50
GLOBAL_VAR = 'global'

''' CLIENT CLASS '''


class Client(BaseClient):

    def __init__(self, url: str, credentials: Dict, verify: bool, proxy: bool, adom: str):
        super().__init__(base_url=url.rstrip('/'), verify=verify, proxy=proxy, ok_codes=(200, 204))
        self.username = credentials["identifier"]
        self.password = credentials["password"]
        self.session_token = self.get_session_token()
        self.adom = adom

    def get_session_token(self, get_new_token: bool = False):
        if get_new_token:
            response = self.fortimanager_http_request('exec', "/sys/login/user",
                                                      json_data={'user': self.username, 'passwd': self.password},
                                                      add_session_token=False)

            demisto.setIntegrationContext({'session': response.get('session')})
            return response.get('session')

        else:
            current_token = demisto.getIntegrationContext().get('session')
            return current_token if current_token else self.get_session_token(get_new_token=True)

    def fortimanager_http_request(self, method: str, url: str, data_in_list: Dict = None, json_data: Dict = None,
                                  range_info: List = None, other_params: Dict = None, add_session_token: bool = True):
        body: Dict = {
            "id": 1,
            "method": method,
            "params": [{
                "url": url
            }],
        }

        if add_session_token:
            body['session'] = self.session_token

        if data_in_list:
            body['params'][0]['data'] = [data_in_list]

        if json_data:
            body['params'][0]['data'] = json_data

        if range_info:
            body['params'][0]['range'] = range_info

        if other_params:
            for param in other_params:
                body['params'][0][param] = other_params.get(param)

        response = self._http_request(
            method='POST',
            url_suffix='jsonrpc',
            json_data=body
        )
        return response

    def fortimanager_api_call(self, method: str, url: str, data_in_list: Dict = None, json_data: Dict = None,
                              range_info: List = None, other_params: Dict = None):
        response = self.fortimanager_http_request(method, url, data_in_list=data_in_list, range_info=range_info,
                                                  other_params=other_params, json_data=json_data)

        # catch session token expiration - fetch new token and retry
        if response.get('result')[0].get('status', {}).get('code') == -11:
            self.session_token = self.get_session_token(get_new_token=True)
            response = self.fortimanager_http_request(method, url, data_in_list=data_in_list, range_info=range_info,
                                                      other_params=other_params, json_data=json_data)

        if response.get('result')[0].get('status', {}).get('code') != 0:
            raise DemistoException(response.get('result')[0].get('status').get('message'))

        return response.get('result')[0].get('data')


def get_global_or_adom(client: Client, args: Dict):
    """Get the ADOM scope on which the command should run.
    If 'adom' command argument is entered use it, otherwise use the default client ADOM parameter.

    """
    adom = args.get('adom') if args.get('adom') else client.adom
    # if the command is reffereing to a specified ADOM then the command should return "adom/{adom_name}"
    # if it refferes to the general system then we should return "global"
    if adom == GLOBAL_VAR:
        return GLOBAL_VAR
    else:
        return f"adom/{adom}"


def setup_request_data(args: Dict, excluded_args: List):
    return {key.replace('_', '-'): args.get(key) for key in args if key not in excluded_args}


def get_specific_entity(entity_name: str):
    if entity_name:
        return f"/{entity_name}"
    else:
        return ""


def get_range_for_list_command(args: Dict):
    first_index = args.get('from')
    last_index = args.get('to')
    list_range = []

    if first_index is not None:
        list_range.append(int(first_index))

    if last_index is not None:
        list_range.append(int(last_index) + 1)

    if list_range:
        return list_range

    else:
        return None


def split_param(args, name, default_val='', skip_if_none=False):
    if not skip_if_none or (skip_if_none and args.get(name)):
        args[name] = args.get(name, default_val).split(',')


def list_adom_devices_command(client, args):
    devices_data = client.fortimanager_api_call("get", f"/dvmdb/{get_global_or_adom(client, args)}/device"
                                                       f"{get_specific_entity(args.get('device'))}")

    headers = ['name', 'ip', 'hostname', 'os_type', 'adm_usr', 'app_ver', 'vdom', 'ha_mode']

    return CommandResults(
        outputs_prefix='FortiManager.Device',
        outputs_key_field='name',
        outputs=devices_data,
        readable_output=tableToMarkdown(f"ADOM {get_global_or_adom(client, args)} Devices", devices_data,
                                        removeNull=True, headerTransform=string_to_table_header, headers=headers),
        raw_response=devices_data,
    )


def list_adom_devices_groups_command(client, args):
    device_groups_data = client.fortimanager_api_call("get", f"/dvmdb/{get_global_or_adom(client, args)}/group"
                                                             f"{get_specific_entity(args.get('group'))}")

    headers = ['name', 'type', 'os_type']

    return CommandResults(
        outputs_prefix='FortiManager.DeviceGroup',
        outputs_key_field='name',
        outputs=device_groups_data,
        readable_output=tableToMarkdown(f"ADOM {get_global_or_adom(client, args)} Device Groups", device_groups_data,
                                        removeNull=True, headerTransform=string_to_table_header, headers=headers),
        raw_response=device_groups_data,
    )


def list_firewall_addresses_command(client, args):
    firewall_addresses = client.fortimanager_api_call("get", f"/pm/config/{get_global_or_adom(client, args)}"
                                                             f"/obj/firewall/address"
                                                             f"{get_specific_entity(args.get('address'))}",
                                                      range_info=get_range_for_list_command(args))

    headers = ['name', 'type', 'subnet', 'start-ip', 'end-ip', 'fqdn', 'wildcard', 'country', 'wildcard-fqdn']

    return CommandResults(
        outputs_prefix='FortiManager.Address',
        outputs_key_field='name',
        outputs=firewall_addresses,
        readable_output=tableToMarkdown("Firewall IPv4 Addresses", firewall_addresses,
                                        removeNull=True, headerTransform=string_to_table_header, headers=headers),
        raw_response=firewall_addresses,
    )


def create_address_command(client, args):
    firewall_addresses = client.fortimanager_api_call("add", f"/pm/config/{get_global_or_adom(client, args)}"
                                                             f"/obj/firewall/address",
                                                      data_in_list=setup_request_data(args, ['adom']))

    return f"Created new Address {firewall_addresses.get('name')}"


def update_address_command(client, args):
    firewall_addresses = client.fortimanager_api_call("update", f"/pm/config/{get_global_or_adom(client, args)}"
                                                                f"/obj/firewall/address",
                                                      data_in_list=setup_request_data(args, ['adom']))

    return f"Updated Address {firewall_addresses.get('name')}"


def delete_address_command(client, args):
    client.fortimanager_api_call("delete", f"/pm/config/{get_global_or_adom(client, args)}"
                                           f"/obj/firewall/address/{args.get('address')}")
    return f"Deleted Address {args.get('address')}"


def list_address_groups_command(client, args):
    address_group = get_specific_entity(args.get('address_group'))
    firewall_address_groups = client.fortimanager_api_call("get", f"/pm/config/"
                                                                  f"{get_global_or_adom(client, args)}"
                                                                  f"/obj/firewall/addrgrp{address_group}",
                                                           range_info=get_range_for_list_command(args))

    headers = ['name', 'member', 'tagging', 'allow-routing']

    return CommandResults(
        outputs_prefix='FortiManager.AddressGroup',
        outputs_key_field='name',
        outputs=firewall_address_groups,
        readable_output=tableToMarkdown("Firewall IPv4 Address Groups", firewall_address_groups,
                                        removeNull=True, headerTransform=string_to_table_header, headers=headers),
        raw_response=firewall_address_groups,
    )


def create_address_group_command(client, args):
    data = setup_request_data(args, ['adom'])
    data['member'] = data.get('member').split(',')
    firewall_address_groups = client.fortimanager_api_call("add", f"/pm/config/"
                                                                  f"{get_global_or_adom(client, args)}"
                                                                  f"/obj/firewall/addrgrp",
                                                           data_in_list=data)

    return f"Created new Address Group {firewall_address_groups.get('name')}"


def update_address_group_command(client, args):
    data = setup_request_data(args, ['adom'])
    data['member'] = data.get('member').split(',')
    firewall_address_groups = client.fortimanager_api_call("update", f"/pm/config/"
                                                                     f"{get_global_or_adom(client, args)}"
                                                                     f"/obj/firewall/addrgrp",
                                                           data_in_list=data)

    return f"Updated Address Group {firewall_address_groups.get('name')}"


def delete_address_group_command(client, args):
    client.fortimanager_api_call("delete", f"/pm/config/{get_global_or_adom(client, args)}"
                                           f"/obj/firewall/addrgrp/{args.get('address_group')}")
    return f"Deleted Address Group {args.get('address_group')}"


def list_service_categories_command(client, args):
    service_categories = client.fortimanager_api_call("get", f"/pm/config/"
                                                             f"{get_global_or_adom(client, args)}/"
                                                             f"obj/firewall/service/category"
                                                             f"{get_specific_entity(args.get('service_category'))}",
                                                      range_info=get_range_for_list_command(args))
    headers = ['name', 'comment']

    return CommandResults(
        outputs_prefix='FortiManager.ServiceCategory',
        outputs_key_field='name',
        outputs=service_categories,
        readable_output=tableToMarkdown("Service Categories", service_categories, removeNull=True,
                                        headerTransform=string_to_table_header, headers=headers),
        raw_response=service_categories,
    )


def list_service_groups_command(client, args):
    service_groups = client.fortimanager_api_call("get", f"/pm/config/"
                                                         f"{get_global_or_adom(client, args)}"
                                                         f"/obj/firewall/service/group"
                                                         f"{get_specific_entity(args.get('service_group'))}",
                                                  range_info=get_range_for_list_command(args))

    headers = ['name', 'member', 'proxy', 'comment']

    return CommandResults(
        outputs_prefix='FortiManager.ServiceGroup',
        outputs_key_field='name',
        outputs=service_groups,
        readable_output=tableToMarkdown("Service Groups", service_groups, removeNull=True,
                                        headerTransform=string_to_table_header, headers=headers),
        raw_response=service_groups,
    )


def create_service_group_command(client, args):
    data = setup_request_data(args, ['adom'])
    data['member'] = data.get('member').split(',')
    service_groups = client.fortimanager_api_call("add", f"/pm/config/"
                                                         f"{get_global_or_adom(client, args)}"
                                                         f"/obj/firewall/service/group",
                                                  data_in_list=data)

    return f"Created new Service Group {service_groups.get('name')}"


def update_service_group_command(client, args):
    data = setup_request_data(args, ['adom'])
    data['member'] = data.get('member').split(',')
    service_groups = client.fortimanager_api_call("update", f"/pm/config/"
                                                            f"{get_global_or_adom(client, args)}"
                                                            f"/obj/firewall/service/group",
                                                  data_in_list=data)

    return f"Updated Service Group {service_groups.get('name')}"


def delete_service_group_command(client, args):
    client.fortimanager_api_call("delete", f"/pm/config/{get_global_or_adom(client, args)}"
                                           f"/obj/firewall/service/group/{args.get('service_group')}")
    return f"Deleted Address Group {args.get('service_group')}"


def list_custom_service_command(client, args):
    custom_services = client.fortimanager_api_call("get", f"/pm/config/"
                                                          f"{get_global_or_adom(client, args)}"
                                                          f"/obj/firewall/service/custom"
                                                          f"{get_specific_entity(args.get('custom_service'))}",
                                                   range_info=get_range_for_list_command(args))

    headers = ['name', 'category', 'protocol', 'iprange', 'fqdn']

    return CommandResults(
        outputs_prefix='FortiManager.CustomService',
        outputs_key_field='name',
        outputs=custom_services,
        readable_output=tableToMarkdown("Custom Services", custom_services, removeNull=True,
                                        headerTransform=string_to_table_header, headers=headers),
        raw_response=custom_services,
    )


def create_custom_service_command(client, args):
    custom_services = client.fortimanager_api_call("add", f"/pm/config/"
                                                          f"{get_global_or_adom(client, args)}"
                                                          f"/obj/firewall/service/custom",
                                                   data_in_list=setup_request_data(args, ['adom']))
    return f"Created new Custom Service {custom_services.get('name')}"


def update_custom_service_command(client, args):
    custom_services = client.fortimanager_api_call("update", f"/pm/config/{get_global_or_adom(client, args)}"
                                                             f"/obj/firewall/service/custom",
                                                   data_in_list=setup_request_data(args, ['adom']))
    return f"Updated Custom Service {custom_services.get('name')}"


def delete_custom_service_command(client, args):
    client.fortimanager_api_call("delete", f"/pm/config/{get_global_or_adom(client, args)}"
                                           f"/obj/firewall/service/custom/{args.get('custom')}")
    return f"Deleted Custom Service {args.get('custom')}"


def list_policy_packages_command(client, args):
    policy_packages = client.fortimanager_api_call("get", f"pm/pkg/{get_global_or_adom(client, args)}"
                                                          f"{get_specific_entity(args.get('policy_package'))}",
                                                   range_info=get_range_for_list_command(args))

    headers = ['name', 'obj_ver', 'type', 'scope_member']

    return CommandResults(
        outputs_prefix='FortiManager.PolicyPackage',
        outputs_key_field='name',
        outputs=policy_packages,
        readable_output=tableToMarkdown("Policy Packages", policy_packages, removeNull=True,
                                        headerTransform=string_to_table_header, headers=headers),
        raw_response=policy_packages,
    )


def create_policy_package_command(client, args):
    package_settings = {
        'central-nat': args.get('central_nat'),
        'consolidated-firewall': args.get('consolidated_firewall'),
        'fwpolicy-implicit-log': args.get('fwpolicy_implicit_log'),
        'fwpolicy6-implicit-log': args.get('fwpolicy6_implicit_log'),
        'inspection-mode': args.get('inspection_mode'),
        'ngfw-mode': args.get('ngfw_mode'),
        'ssl-ssh-profile': args.get('ssl_ssh_profile')
    }

    args['package settings'] = package_settings
    client.fortimanager_api_call("add", f"pm/pkg/{get_global_or_adom(client, args)}",
                                 data_in_list=setup_request_data(args, ['adom', 'central_nat', 'consolidated_firewall',
                                                                        'fwpolicy_implicit_log',
                                                                        'fwpolicy6_implicit_log', 'inspection_mode',
                                                                        'ngfw_mode', 'ssl_ssh_profile']))

    return f"Created new Policy Package {args.get('name')}"


def update_policy_package_command(client, args):
    package_settings = {
        'central-nat': args.get('central_nat'),
        'consolidated-firewall': args.get('consolidated_firewall'),
        'fwpolicy-implicit-log': args.get('fwpolicy_implicit_log'),
        'fwpolicy6-implicit-log': args.get('fwpolicy6_implicit_log'),
        'inspection-mode': args.get('inspection_mode'),
        'ngfw-mode': args.get('ngfw_mode'),
        'ssl-ssh-profile': args.get('ssl_ssh_profile')
    }

    args['package settings'] = package_settings
    client.fortimanager_api_call("update", f"pm/pkg/{get_global_or_adom(client, args)}",
                                 data_in_list=setup_request_data(args, ['adom', 'central_nat', 'consolidated_firewall',
                                                                        'fwpolicy_implicit_log',
                                                                        'fwpolicy6_implicit_log', 'inspection_mode',
                                                                        'ngfw_mode', 'ssl_ssh_profile']))

    return f"Update Policy Package {args.get('name')}"


def delete_policy_package_command(client, args):
    client.fortimanager_api_call("delete", f"pm/pkg/{get_global_or_adom(client, args)}/{args.get('pkg_path')}")
    return f"Deleted Policy Package {args.get('pkg_path')}"


def list_policies_command(client, args):
    policies = client.fortimanager_api_call("get", f"/pm/config/"
                                                   f"{get_global_or_adom(client, args)}"
                                                   f"/pkg/{args.get('package')}/firewall/policy"
                                                   f"{get_specific_entity(args.get('policy_id'))}",
                                            range_info=get_range_for_list_command(args))

    headers = ['policyid', 'name', 'srcintf', 'dstintf', 'srcaddr', 'dstaddr', 'schedule', 'service', 'users', 'action']

    return CommandResults(
        outputs_prefix='FortiManager.PolicyPackage.Policy',
        outputs_key_field='name',
        outputs=policies,
        readable_output=tableToMarkdown(f"ADOM {client.adom} Policy Package {args.get('package')} Policies",
                                        policies, removeNull=True, headerTransform=string_to_table_header,
                                        headers=headers),
        raw_response=policies,
    )


def create_policy_command(client, args):
    if args.get('additional_params'):
        for additional_param in args.get('additional_params').split(','):
            field_and_value = additional_param.split('=')
            args[field_and_value[0]] = field_and_value[1]

    json_data = setup_request_data(args, ['adom', 'package', 'additional_params'])
    split_param(json_data, 'dstaddr', 'all', skip_if_none=True)
    split_param(json_data, 'dstaddr6', 'all', skip_if_none=True)
    split_param(json_data, 'dstintf', 'any')
    split_param(json_data, 'schedule', 'always')
    split_param(json_data, 'service', 'ALL')
    split_param(json_data, 'srcaddr', 'all', skip_if_none=True)
    split_param(json_data, 'srcaddr6', 'all', skip_if_none=True)
    split_param(json_data, 'srcintf', 'any')

    if not (json_data.get('dstaddr') or json_data.get('dstaddr6')):
        raise DemistoException("Please enter 'dstaddr' or 'dstaddr6' command arguments")

    if not (json_data.get('srcaddr') or json_data.get('srcaddr6')):
        raise DemistoException("Please enter 'srcaddr' or 'srcaddr6' command arguments")

    policies = client.fortimanager_api_call("add", f"/pm/config/"
                                                   f"{get_global_or_adom(client, args)}"
                                                   f"/pkg/{args.get('package')}/firewall/policy",
                                            json_data=json_data)

    return f"Created policy with ID {policies.get('policyid')}"


def update_policy_command(client, args):
    if args.get('additional_params'):
        for additional_param in args.get('additional_params').split(','):
            field_and_value = additional_param.split('=')
            args[field_and_value[0]] = field_and_value[1]

    data = setup_request_data(args, ['adom', 'package', 'additional_params'])
    split_param(data, 'dstaddr', 'all', skip_if_none=True)
    split_param(data, 'dstaddr6', 'all', skip_if_none=True)
    split_param(data, 'dstintf', 'any', skip_if_none=True)
    split_param(data, 'schedule', 'always', skip_if_none=True)
    split_param(data, 'service', 'ALL', skip_if_none=True)
    split_param(data, 'srcaddr', 'all', skip_if_none=True)
    split_param(data, 'srcaddr6', 'all', skip_if_none=True)
    split_param(data, 'srcintf', 'any', skip_if_none=True)

    policies = client.fortimanager_api_call("update", f"/pm/config/"
                                                      f"{get_global_or_adom(client, args)}"
                                                      f"/pkg/{args.get('package')}/firewall/policy",
                                            data_in_list=data)

    return f"Updated policy with ID {policies.get('id')}"


def delete_policy_command(client, args):
    client.fortimanager_api_call("delete", f"/pm/config/{get_global_or_adom(client, args)}/pkg/"
                                           f"{args.get('package')}/firewall/policy/{args.get('policy')}")
    return f"Deleted Policy {args.get('policy')}"


def move_policy_command(client, args):
    client.fortimanager_api_call("move", f"/pm/config/{get_global_or_adom(client, args)}"
                                         f"/pkg/{args.get('package')}/firewall/policy/{args.get('policy')}",
                                 other_params=setup_request_data(args, ['adom', 'package', 'policy']))

    return f"Moved policy with ID {args.get('policy')} {args.get('option')} {args.get('target')}"


def list_dynamic_interface_command(client, args):
    dynamic_interfaces = client.fortimanager_api_call("get", f"/pm/config/"
                                                             f"{get_global_or_adom(client, args)}"
                                                             f"/obj/dynamic/interface",
                                                      range_info=get_range_for_list_command(args))

    headers = ['name']

    return CommandResults(
        outputs_prefix='FortiManager.DynamicInterface',
        outputs_key_field='name',
        outputs=dynamic_interfaces,
        readable_output=tableToMarkdown(f"ADOM {client.adom} Dynamic Interfaces",
                                        dynamic_interfaces, removeNull=True, headerTransform=string_to_table_header,
                                        headers=headers),
        raw_response=dynamic_interfaces,
    )


def list_dynamic_address_mapping_command(client, args):
    dynamic_mapping = client.fortimanager_api_call("get", f"/pm/config/{get_global_or_adom(client, args)}"
                                                          f"/obj/firewall/address"
                                                          f"/{args.get('address')}/dynamic_mapping"
                                                          f"{get_specific_entity(args.get('dynamic_mapping'))}",
                                                   range_info=get_range_for_list_command(args))

    headers = ['name', 'type', 'subnet', 'start-ip', 'end-ip', 'fqdn', 'wildcard', 'country', 'wildcard-fqdn']

    return CommandResults(
        outputs_prefix='FortiManager.Address.DynamicMapping',
        outputs_key_field='obj-id',
        outputs=dynamic_mapping,
        readable_output=tableToMarkdown(f"Address {args.get('dynamic_mapping')} Dynamic Mapping",
                                        dynamic_mapping, removeNull=True, headerTransform=string_to_table_header,
                                        headers=headers),
        raw_response=dynamic_mapping,
    )


def create_dynamic_address_mapping_command(client, args):
    client.fortimanager_api_call("add", f"/pm/config/{get_global_or_adom(client, args)}"
                                        f"/obj/firewall/address/{args.get('address')}/dynamic_mapping",
                                 data_in_list=setup_request_data(args, ['adom', 'address']))

    return f"Created new dynamic mapping in address {args.get('address')}"


def update_dynamic_address_mapping_command(client, args):
    client.fortimanager_api_call("update", f"/pm/config/{get_global_or_adom(client, args)}"
                                           f"/obj/firewall/address/{args.get('address')}/dynamic_mapping",
                                 data_in_list=setup_request_data(args, ['adom', 'address']))

    return f"Updated dynamic mapping in address {args.get('address')}"


def delete_dynamic_address_mapping_command(client, args):
    client.fortimanager_api_call("update", f"/pm/config/{get_global_or_adom(client, args)}"
                                           f"/obj/firewall/address/{args.get('address')}/dynamic_mapping/"
                                           f"{args.get('dynamic_mapping')}",
                                 data_in_list=setup_request_data(args, ['adom', 'address']))

    return f"Deleted dynamic mapping {args.get('dynamic_mapping')} in address {args.get('address')}"


def install_policy_package_command(client, args):
    response = client.fortimanager_api_call('exec', "/securityconsole/install/package",
                                            json_data={
                                                'adom_rev_comment': args.get('adom_rev_comment'),
                                                'adom_rev_name': args.get('adom_rev_name'),
                                                'dev_rev_comment': args.get('dev_rev_comment'),
                                                'adom': get_global_or_adom(client, args).replace('adom/', ''),
                                                'pkg': args.get('package'),
                                                'scope': [{
                                                    "name": args.get('name'),
                                                    "vdom": args.get('vdom')
                                                }]
                                            })
    formatted_response = {'id': response.get('task')}
    return CommandResults(
        outputs_prefix='FortiManager.Installation',
        outputs_key_field='id',
        outputs=formatted_response,
        readable_output=f"Installed a policy package {args.get('package')} in ADOM: {get_global_or_adom(client, args)} "
                        f"on Device {args.get('name')} on VDOM {args.get('vdom')}.\nTask ID: {response.get('task')}",
        raw_response=response
    )


def install_policy_package_status_command(client, args):
    task_data = client.fortimanager_api_call('get', f"/task/task/{args.get('task_id')}")

    headers = ['id', 'title', 'adom', 'percent', 'line']

    return CommandResults(
        outputs_prefix='FortiManager.Installation',
        outputs_key_field='id',
        outputs=task_data,
        readable_output=tableToMarkdown(f"Installation Task {args.get('task_id')} Status",
                                        task_data, removeNull=True, headerTransform=string_to_table_header,
                                        headers=headers),
        raw_response=task_data
    )


''' MAIN FUNCTION '''


def main() -> None:
    """main function, parses params and runs command functions

    :return:
    :rtype:
    """

    creds = demisto.params().get('creds')
    base_url = demisto.params().get('url')
    adom = demisto.params().get('adom')
    verify_certificate = not demisto.params().get('insecure', False)
    proxy = demisto.params().get('proxy', False)

    demisto.debug(f'Command being called is {demisto.command()}')
    try:
        client = Client(
            url=base_url,
            credentials=creds,
            verify=verify_certificate,
            proxy=proxy,
            adom=adom
        )

        if demisto.command() == 'test-module':
            # This is the call made when pressing the integration Test button.
            list_adom_devices_command(client, {})
            return_results("ok")

        elif demisto.command() == 'fortimanager-devices-list':
            return_results(list_adom_devices_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-device-groups-list':
            return_results(list_adom_devices_groups_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-list':
            return_results(list_firewall_addresses_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-create':
            return_results(create_address_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-update':
            return_results(update_address_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-delete':
            return_results(delete_address_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-group-list':
            return_results(list_address_groups_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-group-create':
            return_results(create_address_group_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-group-update':
            return_results(update_address_group_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-address-group-delete':
            return_results(delete_address_group_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-service-categories-list':
            return_results(list_service_categories_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-service-group-list':
            return_results(list_service_groups_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-service-group-create':
            return_results(create_service_group_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-service-group-update':
            return_results(update_service_group_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-service-group-delete':
            return_results(delete_service_group_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-custom-service-list':
            return_results(list_custom_service_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-custom-service-create':
            return_results(create_custom_service_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-custom-service-update':
            return_results(update_custom_service_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-custom-service-delete':
            return_results(delete_custom_service_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-package-list':
            return_results(list_policy_packages_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-package-create':
            return_results(create_policy_package_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-package-update':
            return_results(update_policy_package_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-package-delete':
            return_results(delete_policy_package_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-list':
            return_results(list_policies_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-create':
            return_results(create_policy_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-update':
            return_results(update_policy_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-delete':
            return_results(delete_policy_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-move':
            return_results(move_policy_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-dynamic-interface-list':
            return_results(list_dynamic_interface_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-dynamic-address-mappings-list':
            return_results(list_dynamic_address_mapping_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-dynamic-address-mappings-create':
            return_results(create_dynamic_address_mapping_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-dynamic-address-mappings-update':
            return_results(update_dynamic_address_mapping_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-dynamic-address-mapping-delete':
            return_results(delete_dynamic_address_mapping_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-package-install':
            return_results(install_policy_package_command(client, demisto.args()))

        elif demisto.command() == 'fortimanager-firewall-policy-package-install-status':
            return_results(install_policy_package_status_command(client, demisto.args()))

    # Log exceptions and return errors
    except Exception:
        demisto.error(traceback.format_exc())  # print the traceback
        return_error(f'Failed to execute {demisto.command()} command.\nError:\n{traceback.format_exc()}')


''' ENTRY POINT '''

if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()
