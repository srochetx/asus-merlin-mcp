#!/usr/bin/env python3
r"""
___  ____  _____   ____  _____ ____ _ __ _____
\  \/ (__)/  ___)_/    \/  _  )    | |  | ____)
 \    |  |  |(_  _) () |     (  () | |  |___  \
  \   |__|____   |\____|__|\  \____|____|      )
   \_/        `--'          `--'         \____/
        P  R  o  G  R  A  M  M  i  N  G
<========================================[KCS]=>
  Developer: Ken C. Soukup
  Project  : MCP Server for ASUS Router
  Purpose  : Use AI Agents for managing ASUS routers running Asuswrt-Merlin firmware via SSH/SCP.
<=================================[10/08/2025]=>
  Home:  Asuswrt-Merlin Firmware  --  https://www.asuswrt-merlin.net/
  Help:  SNBForums ASUS WiFi      --  https://www.snbforums.com/forums/asus-wi-fi.37/
"""

__project__ = "MCP Server for ASUS Router"
__version__ = "3.0.1"
__author__ = "Ken C. Soukup"
__company__ = "Vigorous Programming"
__minted__ = "2025"

import logging
from collections.abc import Callable, Sequence
from typing import Any, TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.types import EmbeddedResource, ImageContent, TextContent

# Import configuration
from config.router_config import ROUTER_CONFIG

# Import core infrastructure
from core.ssh_client import RouterSSHClient

# Import all tool handlers
from tools import (
    handle_add_dhcp_reservation,
    handle_add_keyword_filter,
    handle_add_mac_filter,
    handle_add_network_service_filter_rule,
    handle_add_url_filter,
    handle_add_vpn_routing_policy,
    handle_block_device_internet,
    handle_download_file,
    handle_execute_command,
    handle_get_aiprotection_status,
    handle_get_all_network_devices,
    handle_get_connected_devices,
    handle_get_firewall_status,
    handle_get_keyword_filter_status,
    handle_get_network_service_filter_status,
    handle_get_nvram_variable,
    handle_get_router_info,
    handle_get_system_log,
    handle_get_url_filter_status,
    handle_get_vpn_server_status,
    handle_get_vpn_server_users,
    handle_get_vpn_status,
    handle_get_wifi_status,
    handle_list_blocked_devices,
    handle_list_dhcp_reservations,
    handle_list_keyword_filters,
    handle_list_mac_filters,
    handle_list_network_service_filter_rules,
    handle_list_processes,
    handle_list_url_filters,
    handle_list_vpn_policies,
    handle_read_file,
    handle_reboot_router,
    handle_remove_dhcp_reservation,
    handle_remove_keyword_filter,
    handle_remove_mac_filter,
    handle_remove_network_service_filter_rule,
    handle_remove_url_filter,
    handle_remove_vpn_routing_policy,
    handle_restart_service,
    handle_set_firewall_config,
    handle_set_network_service_filter_mode,
    handle_set_network_service_filter_schedule,
    handle_set_nvram_variable,
    handle_set_system_log_config,
    handle_set_url_filter_mode,
    handle_upload_file,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("asus-merlin-mcp")

# Initialize MCP server and router connection
mcp = FastMCP("asus-merlin-router")
router = RouterSSHClient(ROUTER_CONFIG)

ToolResponse = Sequence[TextContent | ImageContent | EmbeddedResource]


class VpnPassthroughConfig(TypedDict, total=False):
    pptp: bool
    l2tp: bool
    ipsec: bool
    rtsp: bool
    h323: bool
    sip: bool
    pppoe_relay: bool


def _to_arguments(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def _call_handler(
    handler: Callable[[RouterSSHClient, Any], ToolResponse], arguments: dict[str, Any]
) -> ToolResponse:
    try:
        return handler(router, arguments)
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return [TextContent(type="text", text=f"Error executing tool: {str(e)}")]


@mcp.tool()
def get_router_info() -> ToolResponse:
    """Get router system information (uptime, memory, CPU, firmware version)"""
    return _call_handler(handle_get_router_info, {})


@mcp.tool()
def get_connected_devices() -> ToolResponse:
    """List all devices connected to the router (via DHCP)"""
    return _call_handler(handle_get_connected_devices, {})


@mcp.tool()
def get_all_network_devices(filter_type: str | None = None) -> ToolResponse:
    """Get comprehensive list of all network devices (DHCP + static + ARP) with detailed info"""
    return _call_handler(
        handle_get_all_network_devices,
        _to_arguments(filter_type=filter_type),
    )


@mcp.tool()
def get_wifi_status() -> ToolResponse:
    """Get WiFi status for all radios (2.4GHz, 5GHz, etc.)"""
    return _call_handler(handle_get_wifi_status, {})


@mcp.tool()
def restart_service(service_name: str) -> ToolResponse:
    """Restart a specific router service (e.g., wireless, vpnclient1, httpd)"""
    return _call_handler(handle_restart_service, {"service_name": service_name})


@mcp.tool()
def reboot_router(confirm: bool) -> ToolResponse:
    """Reboot the router. WARNING: This will disconnect all clients."""
    return _call_handler(handle_reboot_router, {"confirm": confirm})


@mcp.tool()
def get_nvram_variable(variable_name: str) -> ToolResponse:
    """Get the value of a specific NVRAM variable"""
    return _call_handler(handle_get_nvram_variable, {"variable_name": variable_name})


@mcp.tool()
def set_nvram_variable(
    variable_name: str,
    value: str,
    commit: bool = False,
) -> ToolResponse:
    """Set a NVRAM variable value. WARNING: Incorrect values can break router configuration."""
    return _call_handler(
        handle_set_nvram_variable,
        {"variable_name": variable_name, "value": value, "commit": commit},
    )


@mcp.tool()
def execute_command(command: str) -> ToolResponse:
    """Execute a custom command on the router via SSH. WARNING: NEVER use this for file operations (reading, writing, editing files). ALWAYS use read_file, upload_file, or download_file tools for file operations. Do NOT use heredoc (cat << EOF) or echo for file writes - use upload_file instead."""
    return _call_handler(handle_execute_command, {"command": command})


@mcp.tool()
def read_file(file_path: str, max_lines: int = 100) -> ToolResponse:
    """Read contents of a file on the router"""
    return _call_handler(
        handle_read_file,
        {"file_path": file_path, "max_lines": max_lines},
    )


@mcp.tool()
def upload_file(local_path: str, remote_path: str) -> ToolResponse:
    """Upload a file to the router via SCP with MD5 verification. Use this for creating or editing router files. Workflow: 1) download_file to get current content, 2) edit locally, 3) upload_file to save changes. NEVER use execute_command with heredoc for file edits."""
    return _call_handler(
        handle_upload_file,
        {"local_path": local_path, "remote_path": remote_path},
    )


@mcp.tool()
def download_file(remote_path: str, local_path: str) -> ToolResponse:
    """Download a file from the router via SCP"""
    return _call_handler(
        handle_download_file,
        {"remote_path": remote_path, "local_path": local_path},
    )


@mcp.tool()
def get_vpn_status() -> ToolResponse:
    """Get status of VPN clients and servers"""
    return _call_handler(handle_get_vpn_status, {})


@mcp.tool()
def get_aiprotection_status() -> ToolResponse:
    """Get AiProtection (Trend Micro) security status including malicious sites blocking, two-way IPS, and infected device prevention"""
    return _call_handler(handle_get_aiprotection_status, {})


@mcp.tool()
def get_vpn_server_status() -> ToolResponse:
    """Get detailed VPN server status including connected clients"""
    return _call_handler(handle_get_vpn_server_status, {})


@mcp.tool()
def get_vpn_server_users() -> ToolResponse:
    """Get list of users authorized to connect to VPN servers"""
    return _call_handler(handle_get_vpn_server_users, {})


@mcp.tool()
def get_system_log(lines: int | None = None, filter: str | None = None) -> ToolResponse:
    """Get system log entries from the router with optional filtering"""
    return _call_handler(handle_get_system_log, _to_arguments(lines=lines, filter=filter))


@mcp.tool()
def set_system_log_config(
    message_loglevel: str | None = None,
    log_level: str | None = None,
    log_ipaddr: str | None = None,
    log_port: int | None = None,
) -> ToolResponse:
    """Configure system log settings (log levels, remote syslog server)"""
    return _call_handler(
        handle_set_system_log_config,
        _to_arguments(
            message_loglevel=message_loglevel,
            log_level=log_level,
            log_ipaddr=log_ipaddr,
            log_port=log_port,
        ),
    )


@mcp.tool()
def list_processes(filter: str | None = None) -> ToolResponse:
    """List running processes on the router"""
    return _call_handler(handle_list_processes, _to_arguments(filter=filter))


@mcp.tool()
def get_firewall_status() -> ToolResponse:
    """Get comprehensive firewall status and configuration including main firewall, DoS protection, logging, WAN ping response, VPN passthrough settings, and IPv6 firewall"""
    return _call_handler(handle_get_firewall_status, {})


@mcp.tool()
def set_firewall_config(
    enable_firewall: bool | None = None,
    enable_dos_protection: bool | None = None,
    log_mode: str | None = None,
    respond_to_wan_ping: bool | None = None,
    enable_ipv6_firewall: bool | None = None,
    vpn_passthrough: VpnPassthroughConfig | None = None,
) -> ToolResponse:
    """Configure firewall settings including enable/disable main firewall, DoS protection, logging mode, WAN ping response, IPv6 firewall, and VPN passthrough protocols (PPTP, L2TP, IPSec, RTSP, H.323, SIP, PPPoE)"""
    return _call_handler(
        handle_set_firewall_config,
        _to_arguments(
            enable_firewall=enable_firewall,
            enable_dos_protection=enable_dos_protection,
            log_mode=log_mode,
            respond_to_wan_ping=respond_to_wan_ping,
            enable_ipv6_firewall=enable_ipv6_firewall,
            vpn_passthrough=vpn_passthrough,
        ),
    )


@mcp.tool()
def get_url_filter_status() -> ToolResponse:
    """Get global URL filter status including enabled state, filter mode (blacklist/whitelist), number of rules, and schedule"""
    return _call_handler(handle_get_url_filter_status, {})


@mcp.tool()
def add_url_filter(url_pattern: str) -> ToolResponse:
    """Add URL pattern to global filter list (blacklist or whitelist depending on mode)"""
    return _call_handler(handle_add_url_filter, {"url_pattern": url_pattern})


@mcp.tool()
def remove_url_filter(url_pattern: str) -> ToolResponse:
    """Remove URL pattern from global filter list"""
    return _call_handler(handle_remove_url_filter, {"url_pattern": url_pattern})


@mcp.tool()
def list_url_filters() -> ToolResponse:
    """List all configured URL filter rules with status and mode"""
    return _call_handler(handle_list_url_filters, {})


@mcp.tool()
def set_url_filter_mode(mode: str) -> ToolResponse:
    """Set URL filter mode to blacklist (block listed URLs) or whitelist (allow only listed URLs)"""
    return _call_handler(handle_set_url_filter_mode, {"mode": mode})


@mcp.tool()
def get_keyword_filter_status() -> ToolResponse:
    """Get keyword filter status including enabled state, number of rules, and schedule"""
    return _call_handler(handle_get_keyword_filter_status, {})


@mcp.tool()
def add_keyword_filter(keyword: str) -> ToolResponse:
    """Add keyword to filter list (blocks URLs containing the keyword)"""
    return _call_handler(handle_add_keyword_filter, {"keyword": keyword})


@mcp.tool()
def remove_keyword_filter(keyword: str) -> ToolResponse:
    """Remove keyword from filter list"""
    return _call_handler(handle_remove_keyword_filter, {"keyword": keyword})


@mcp.tool()
def list_keyword_filters() -> ToolResponse:
    """List all configured keyword filter rules"""
    return _call_handler(handle_list_keyword_filters, {})


@mcp.tool()
def get_network_service_filter_status() -> ToolResponse:
    """Get network service filter status including deny list and allow list configuration, rules, and schedule"""
    return _call_handler(handle_get_network_service_filter_status, {})


@mcp.tool()
def list_network_service_filter_rules(list_type: str) -> ToolResponse:
    """List network service filter rules for deny or allow list"""
    return _call_handler(
        handle_list_network_service_filter_rules,
        {"list_type": list_type},
    )


@mcp.tool()
def add_network_service_filter_rule(
    list_type: str,
    dest_port: str,
    source_ip: str | None = None,
    source_port: str | None = None,
    dest_ip: str | None = None,
    protocol: str = "TCP",
) -> ToolResponse:
    """Add network service filter rule to block/allow specific services by IP and port. Deny list blocks services during schedule. Allow list only allows services during schedule. Leave source IP blank to apply to all devices."""
    return _call_handler(
        handle_add_network_service_filter_rule,
        _to_arguments(
            list_type=list_type,
            source_ip=source_ip,
            source_port=source_port,
            dest_ip=dest_ip,
            dest_port=dest_port,
            protocol=protocol,
        ),
    )


@mcp.tool()
def remove_network_service_filter_rule(
    list_type: str,
    dest_port: str,
    protocol: str,
    source_ip: str | None = None,
    source_port: str | None = None,
    dest_ip: str | None = None,
) -> ToolResponse:
    """Remove network service filter rule by matching all criteria exactly"""
    return _call_handler(
        handle_remove_network_service_filter_rule,
        _to_arguments(
            list_type=list_type,
            source_ip=source_ip,
            source_port=source_port,
            dest_ip=dest_ip,
            dest_port=dest_port,
            protocol=protocol,
        ),
    )


@mcp.tool()
def set_network_service_filter_mode(list_type: str, enabled: bool) -> ToolResponse:
    """Enable or disable network service filter deny/allow list"""
    return _call_handler(
        handle_set_network_service_filter_mode,
        {"list_type": list_type, "enabled": enabled},
    )


@mcp.tool()
def set_network_service_filter_schedule(
    list_type: str,
    days: str,
    weekday_start: str,
    weekday_end: str,
    weekend_start: str | None = None,
    weekend_end: str | None = None,
) -> ToolResponse:
    """Configure network service filter schedule (active days and time ranges). Format: days as 7-digit string (Sun-Sat, 1=active), times in HHMM format (e.g., 0800 for 8:00 AM)"""
    return _call_handler(
        handle_set_network_service_filter_schedule,
        _to_arguments(
            list_type=list_type,
            days=days,
            weekday_start=weekday_start,
            weekday_end=weekday_end,
            weekend_start=weekend_start,
            weekend_end=weekend_end,
        ),
    )


@mcp.tool()
def add_mac_filter(
    mac_address: str,
    filter_type: str = "blacklist",
    radio: str = "both",
    description: str | None = None,
) -> ToolResponse:
    """Add device to MAC filter (whitelist or blacklist) for WiFi access control"""
    return _call_handler(
        handle_add_mac_filter,
        _to_arguments(
            mac_address=mac_address,
            filter_type=filter_type,
            radio=radio,
            description=description,
        ),
    )


@mcp.tool()
def remove_mac_filter(mac_address: str, radio: str = "both") -> ToolResponse:
    """Remove device from MAC filter"""
    return _call_handler(
        handle_remove_mac_filter,
        {"mac_address": mac_address, "radio": radio},
    )


@mcp.tool()
def list_mac_filters() -> ToolResponse:
    """Show current MAC filters with friendly formatting"""
    return _call_handler(handle_list_mac_filters, {})


@mcp.tool()
def add_dhcp_reservation(
    mac_address: str,
    ip_address: str,
    dns: str | None = None,
    hostname: str | None = None,
) -> ToolResponse:
    """Reserve IP address for specific MAC address (static DHCP lease)"""
    return _call_handler(
        handle_add_dhcp_reservation,
        _to_arguments(
            mac_address=mac_address,
            ip_address=ip_address,
            dns=dns,
            hostname=hostname,
        ),
    )


@mcp.tool()
def remove_dhcp_reservation(
    mac_address: str | None = None,
    ip_address: str | None = None,
) -> ToolResponse:
    """Remove DHCP reservation by MAC or IP address"""
    return _call_handler(
        handle_remove_dhcp_reservation,
        _to_arguments(mac_address=mac_address, ip_address=ip_address),
    )


@mcp.tool()
def list_dhcp_reservations() -> ToolResponse:
    """Show all current DHCP reservations"""
    return _call_handler(handle_list_dhcp_reservations, {})


@mcp.tool()
def block_device_internet(
    mac_address: str,
    enabled: bool,
    description: str | None = None,
) -> ToolResponse:
    """Block or unblock device from internet access (parental controls)"""
    return _call_handler(
        handle_block_device_internet,
        _to_arguments(
            mac_address=mac_address,
            enabled=enabled,
            description=description,
        ),
    )


@mcp.tool()
def list_blocked_devices() -> ToolResponse:
    """Show devices with internet access restrictions"""
    return _call_handler(handle_list_blocked_devices, {})


@mcp.tool()
def add_vpn_routing_policy(
    mac_address: str,
    vpn_client_number: int,
    description: str | None = None,
) -> ToolResponse:
    """Route specific device through VPN client using VPN Director (Asuswrt-Merlin firmware only). Adds device to VPN Director routing to route all its traffic through selected VPN client (1-5). Requires Merlin firmware - stock ASUS firmware not supported."""
    return _call_handler(
        handle_add_vpn_routing_policy,
        _to_arguments(
            mac_address=mac_address,
            vpn_client_number=vpn_client_number,
            description=description,
        ),
    )


@mcp.tool()
def remove_vpn_routing_policy(mac_address: str) -> ToolResponse:
    """Remove device from VPN Director routing (Asuswrt-Merlin firmware only). Device will return to normal routing (no VPN). Requires Merlin firmware - stock ASUS firmware not supported."""
    return _call_handler(
        handle_remove_vpn_routing_policy,
        {"mac_address": mac_address},
    )


@mcp.tool()
def list_vpn_policies() -> ToolResponse:
    """List all VPN Director routing rules (Asuswrt-Merlin firmware only). Shows which devices are configured to route through which VPN clients. Requires Merlin firmware - stock ASUS firmware not supported."""
    return _call_handler(handle_list_vpn_policies, {})


if __name__ == "__main__":
    mcp.run()
