---
name: asus-merlin-router-ops
description: Operate an Asuswrt-Merlin router through the asus-merlin-mcp SSH-based MCP server — diagnostics (WAN/ISP, WiFi RF, Ethernet port speeds, DHCP/DNS, VPN tunnels), configuration changes (NVRAM, firewall, filters, DHCP reservations, VPN Director routing), and safe JFFS/Entware scripting. Use whenever a user asks to check, troubleshoot, or change anything on their ASUS router running Asuswrt-Merlin firmware.
---

# ASUS Merlin Router Operations

You are operating a physical home/SOHO router running **Asuswrt-Merlin** firmware over SSH via
the `asus-merlin-mcp` server (`RouterSSHClient`, `core/ssh_client.py`). Every command you issue
runs on real hardware in front of real traffic. Correctness and restraint matter more than speed.

All facts below (NVRAM variable names, service names, file paths, script hook names) are verified
against two sources: the official wiki (`RMerl/asuswrt-merlin.ng.wiki`) and this server's own
source (`config/constants.py`, `tools/*.py`, `core/ssh_client.py`). Where the wiki did not document
a specific detail (e.g. exact `robocfg` field format, DNS Director's internal NVRAM keys), that is
called out explicitly — treat those spots as "verify empirically," not as a fixed known-good string.

---

## Section 1 — Performance & Execution Rules

1. **Prefer the dedicated MCP tool over raw `execute_command`.** The ~45 tools registered in
   `asus_merlin_mcp.py` already handle ASUS's non-standard NVRAM list format
   (`<item1>item2>item3>`, parsed by `utils/nvram_parser.py`) and write files with MD5
   verification (`RouterSSHClient.write_file_content`). Reach for `execute_command` only for
   read-only diagnostics that have no dedicated tool (e.g. `wl -i <if> assoclist`, `robocfg show`,
   `wg show`, `ip route`).

2. **Batch read-only NVRAM/status lookups into one command.** Don't make five SSH round trips for
   five `nvram get` calls — semicolon-chain them, exactly like the server itself does:
   ```
   nvram get TM_EULA; nvram get wrs_protect_enable; nvram get wrs_mals_enable; \
   nvram get wrs_vp_enable; nvram get wrs_cc_enable; nvram get bwdpi_sig_ver
   ```
   (this is the real batch `get_aiprotection_status` sends). Apply the same pattern to any
   multi-variable read you construct yourself.

3. **Cache session-static facts.** Firmware version/buildno, router model, `wl0_ifname` /
   `wl1_ifname`, LAN subnet (`lan_ipaddr`/`lan_netmask`) rarely change mid-session. Fetch once via
   `get_router_info`, reuse for the rest of the conversation instead of re-querying every turn.

4. **Never write files with `execute_command`.** The `execute_command` tool's own description
   forbids heredoc (`cat <<EOF`) or `echo >` for file writes. The only sanctioned file-edit
   workflow is: `download_file` (or `read_file`) → edit locally → `upload_file`. This is not a
   style preference — SSH heredocs are fragile against embedded shells and bypass the MD5
   verification `upload_file` performs.

5. **One destructive action per confirmed user intent.** Don't call `restart_service` or
   `reboot_router` speculatively "just in case" — each restart drops active connections
   (WiFi deauth on `restart_wireless`, VPN tunnel drop on `restart_vpnclientN`, DHCP client
   re-lease on `restart_dnsmasq`). Diagnose fully, propose the single fix, then execute it once.

---

## Section 2 — Command & Parameter Lookup Table

| User intent | MCP tool | Underlying command / NVRAM keys | Healthy signal |
|---|---|---|---|
| Firmware/uptime/model | `get_router_info` | `nvram get firmver; nvram get buildno` | Non-empty version string, e.g. `386.14` |
| Connected devices (DHCP) | `get_connected_devices` | parses DHCP lease table | List of MAC/IP/hostname entries |
| Full device inventory | `get_all_network_devices` | DHCP + `dhcp_staticlist`/`dhcp_reservelist` + `cat /proc/net/arp` + `/etc/hosts` | Devices resolve with consistent IP across sources |
| WiFi radio status | `get_wifi_status` | `nvram get wl0_ifname`/`wl1_ifname`, then `wl -i <ifname> status` | `Radio: enabled` / `state: associated` type output per radio |
| Restart a service | `restart_service(service_name)` | `service restart_<name>` — real names: `wireless`, `dnsmasq`, `firewall`, `httpd`, `vpnclient1`..`vpnclient5` | Exit code 0; service-specific NVRAM `_state` flips back to running |
| Reboot router | `reboot_router(confirm=true)` | `service reboot` | Connection drops (expected); router returns after ~60-120s |
| Read NVRAM var | `get_nvram_variable(variable_name)` | `nvram get <var>` | Returns current value (empty string is valid for unset vars) |
| Write NVRAM var | `set_nvram_variable(variable_name, value, commit)` | `nvram set <var>='<value>'` [`; nvram commit`] | Read-back matches; note many vars need a service restart, not just `commit`, to take effect (`User-scripts.md`) |
| Raw diagnostic command | `execute_command(command)` | any read-only shell command | — (never for file writes; see Section 1 rule 4) |
| Read/write arbitrary file | `read_file` / `upload_file` / `download_file` | SFTP with MD5 verify, shell-hexdump fallback | MD5 on router matches local MD5 |
| MAC allow/deny list | `add_mac_filter` / `remove_mac_filter` / `list_mac_filters` | `wl0_maclist`/`wl1_maclist`, `wl0_macmode`/`wl1_macmode` → `service restart_wireless` | Device with listed MAC can/cannot associate |
| DHCP static reservation | `add_dhcp_reservation` / `remove_dhcp_reservation` / `list_dhcp_reservations` | `dhcp_staticlist` or `dhcp_reservelist` (format `<MAC>IP>DNS>hostname>`) → `service restart_dnsmasq` | Device receives the reserved IP on next lease renewal |
| URL blacklist/whitelist | `add_url_filter` / `remove_url_filter` / `list_url_filters` / `set_url_filter_mode` | `url_enable_x`, `url_mode_x` (0=blacklist,1=whitelist), `url_rulelist` → `service restart_firewall` | Rule appears in `list_url_filters`; blocked domain fails to resolve/connect from LAN |
| Keyword filter | `add_keyword_filter` / `remove_keyword_filter` / `list_keyword_filters` | `keyword_enable_x`, `keyword_rulelist` → `service restart_firewall` | Same pattern as URL filter |
| LAN→WAN service filter (deny/allow list) | `add/remove_network_service_filter_rule`, `set_network_service_filter_mode`, `set_network_service_filter_schedule` | Deny: `fw_lw_enable_x`/`filter_lwlist`/`filter_lw_date_x`/`filter_lw_time_x`/`filter_lw_time2_x`; Allow: `fw_wl_enable_x`/`filter_wllist`/(same date/time pattern) → `service restart_firewall` | Rule shows in `get_network_service_filter_status` |
| Per-device internet block (parental control) | `block_device_internet` / `list_blocked_devices` | `MULTIFILTER_ALL` (master), `MULTIFILTER_ENABLE`, `MULTIFILTER_MAC`, `MULTIFILTER_DEVICENAME` (parallel arrays) → `service restart_firewall` | Device appears in `list_blocked_devices`; loses WAN access |
| Firewall / passthrough config | `get_firewall_status` / `set_firewall_config` | `fw_enable_x`, `fw_dos_x`, `fw_log_x`, `misc_ping_x`, `fw_pt_{pptp,l2tp,ipsec,rtsp,h323,sip,pppoerelay}` → `nvram commit` → `service restart_firewall` | Config read-back matches request |
| VPN client status | `get_vpn_status` | `nvram get vpn_client1_state; nvram get vpn_client2_state; ps \| grep vpn` | `state=2` = connected/running |
| VPN server status | `get_vpn_server_status` | `vpn_server{1,2}_state/_proto/_port/_sn/_if`, `ip addr show tun{N}1`, `/etc/openvpn/server{N}/status` `CLIENT_LIST` lines | `state=2`; client list shows expected peers |
| VPN server authorized users | `get_vpn_server_users` | `cat /etc/passwd` | List of local system accounts (mask password hash field, see Section 5) |
| VPN Director routing rule (Merlin only) | `add_vpn_routing_policy` / `remove_vpn_routing_policy` / `list_vpn_policies` | File-based, **not** NVRAM: `/jffs/openvpn/vpndirector_rulelist`, format `<enable>description>localIP>remoteIP>interface>`, interfaces `OVPN1`-`OVPN5` | Rule appears in `list_vpn_policies`; device's traffic egresses via tunnel IP. **Requires Merlin firmware** — stock ASUS uses `vpnc_dev_policy_list` (VPN Fusion) instead and these tools refuse to run against it |
| System log | `get_system_log` / `set_system_log_config` | `message_loglevel`, `log_level`, `log_ipaddr`, `log_port` | Log lines returned; remote syslog reachable if configured |
| AiProtection (Trend Micro) status | `get_aiprotection_status` | `TM_EULA`, `wrs_protect_enable`, `wrs_mals_enable`, `wrs_vp_enable`, `wrs_cc_enable`, `bwdpi_sig_ver` | `wrs_*_enable=1` for active protections; non-empty signature version |
| List running processes | `list_processes(filter)` | `ps` (optionally grepped) | — |

---

## Section 3 — Complete Diagnostic Workflows

### 3.1 WAN / ISP connectivity
1. `get_router_info` → confirm firmware/uptime aren't mid-reboot.
2. `execute_command("nvram get wan0_state_t; nvram get wan0_ipaddr; nvram get wan0_gateway; nvram get wan_dns")`
   — `wan0_state_t=2` means connected; anything else (0/1/4-6) means down/negotiating/stopped
   (see `wan-event` event list below).
3. `execute_command("ping -c 3 <wan0_gateway>")` — confirms link to ISP's first hop.
4. `execute_command("ping -c 3 8.8.8.8")` — confirms upstream routing past the ISP edge.
5. If gateway ping fails but WAN state shows connected: physical/ISP-side issue, not router config.
6. If DNS resolution fails but IP ping succeeds: check `wan_dns`, then Section 3.4 (dnsmasq).
7. If a custom `/jffs/scripts/wan-event` exists, note it fires on every WAN transition
   (`init`, `connecting`, `connected`, `disconnected`, `stopped`, `disabled`, `stopping`) and could
   be interfering — read it with `read_file` before assuming a router bug.

### 3.2 WiFi RF / association issues
1. `get_wifi_status` — confirms radio enabled, SSID, and firmware-reported per-radio status
   (uses `wl -i <wl0_ifname|wl1_ifname> status` internally).
2. For connected-client detail not in that tool: `execute_command("wl -i <ifname> assoclist")`
   lists associated MAC addresses per radio.
3. Per-client signal quality: `execute_command("wl -i <ifname> rssi <mac>")` — typical healthy
   range is roughly -30 to -70 dBm; below -75 dBm usually explains slow/dropping clients.
4. Cross-reference with `get_connected_devices` to map MAC → hostname/IP.
5. If a specific device won't associate at all, check `list_mac_filters` — it may be blocked by
   `wl0_macmode`/`wl1_macmode` being set to deny with that MAC listed.
6. Channel/interference issues aren't exposed by a dedicated tool — `execute_command("wl -i <ifname> channel")`
   reports the active channel; changing it is an NVRAM (`wl0_chanspec`) + `restart_wireless` operation,
   which will briefly deauth all clients on that radio — confirm with the user first.

### 3.3 Ethernet port link speeds (robocfg)
1. `execute_command("robocfg show")` — dumps the Broadcom switch's per-port link/speed/duplex
   state. This command is confirmed real (used for VLAN port assignment in the wiki's
   Link-Aggregation guide, e.g. `robocfg vlan 1 ports "1 2 5*"`), but the exact output field
   layout is switch-chip-dependent and was **not** captured in the wiki text reviewed for this
   skill — read the output empirically rather than pattern-matching a fixed "healthy" string.
   Look for consistent indicators regardless of exact format: a port marked down/unlinked when a
   cable is known to be plugged in, or a negotiated speed (10/100/1000) far below the cable/NIC
   capability, both indicate a physical-layer problem (cable, NIC, or port fault) rather than a
   configuration one.
2. If a specific LAN port is suspect, correlate with `get_connected_devices`/`cat /proc/net/arp`
   to confirm which device is actually on that port before concluding it's faulty.

### 3.4 DHCP pool / DNS resolver (dnsmasq)
1. `execute_command("nvram get lan_ipaddr; nvram get lan_netmask; nvram get dhcp_start; nvram get dhcp_end; nvram get dhcp_lease")`
   — confirms the configured pool.
2. `execute_command("cat /var/lib/misc/dnsmasq.leases")` — live lease table (format:
   `timestamp MAC IP hostname client-id`); this is the exact path this server's own VPN Director
   code reads to resolve a MAC to its current IP.
3. `read_file("/etc/dnsmasq.conf")` — the firmware-generated live config, useful for confirming
   what actually got applied (vs. what NVRAM says was requested).
4. If leases are exhausted (`dhcp_start`..`dhcp_end` range full): either shrink lease time
   (`dhcp_lease`) or expand the pool — both are `nvram set` + `service restart_dnsmasq`.
5. **DNS Director** (per-client forced-DNS feature, LAN webui tab) has no NVRAM variable names
   documented in the wiki page reviewed for this skill — don't guess at NVRAM keys for it. Instead
   inspect its effect indirectly: check `/etc/dnsmasq.conf` for per-client `--server=/#/<ip>`-style
   redirection lines, and be aware it can break *local* hostname resolution for redirected clients
   by design (documented side effect) — this is often the actual root cause when a user reports
   "device on my network won't resolve my other devices."

### 3.5 OpenVPN / WireGuard tunnels
1. `get_vpn_status` — quick client state check (`vpn_client{1,2}_state`, `ps | grep vpn`).
2. `get_vpn_server_status` — full server detail: state, protocol, port, subnet, tunnel interface
   IP, and connected-client table (parsed from `/etc/openvpn/server{N}/status`'s `CLIENT_LIST`
   lines: common name, real IP, virtual IP, bytes sent/received, connect time).
3. For WireGuard, which has no dedicated status tool: `execute_command("wg show")` — lists
   interfaces, peers, handshake age, and transfer counters. A peer with no recent handshake
   (`latest handshake: N minutes/hours ago`, or absent) is not currently connected.
4. If a client is up but traffic isn't routing through it as expected: check
   `list_vpn_policies` — VPN Director rules apply in strict priority order (WAN bypass first,
   then OpenVPN1→5, then WireGuard1→5; Dual-WAN routes outrank all VPN Director rules), and a
   client's killswitch will block *lower-priority* clients' traffic if the higher-priority one's
   tunnel is down.
5. Relevant script hooks if custom automation is involved: `openvpn-event` (fires on server
   start/stop or client connect, same semantics as OpenVPN's up/down scripts, with `$script_type`
   indicating which), and `wgclient-start`/`wgclient-stop`/`wgserver-start`/`wgserver-stop`.

---

## Section 4 — JFFS Scripting & Entware Standards

**Never edit anything under `/etc/` directly.** Files there are dynamically regenerated by the
firmware on every service restart/boot; a manual edit will be silently overwritten and gives a
false sense of persistence. The only sanctioned customization points:

1. **Config overrides — `/jffs/configs/`**. Two supported forms, verified from the current list
   in `Custom-config-files.md`:
   - `/jffs/configs/<name>.add` — appended to the firmware-generated file (e.g.
     `dnsmasq.conf.add`, `hosts.add` isn't valid — check the specific file's `.add`-only status).
   - `/jffs/configs/<name>` — fully replaces the firmware-generated file (only supported for a
     subset — many entries are `.add`-only, e.g. `cake-qos.conf`, `exports`, `group`, `gshadow`,
     `passwd`, `shadow`, `profile`, `stubby.yml`). When replacing rather than appending, you must
     reproduce every field the firmware would have dynamically generated — this is high-risk;
     prefer `.add` whenever the target supports it.
   - Full name list current at review time: `adisk.service`, `afpd.service`, `avahi-daemon.conf`,
     `cake-qos.conf` (`.add` only), `dhcp6s.conf`, `dnsmasq.conf`, `dnsmasq-INDEX.conf` (SDN,
     `.add` only), `exports` (`.add` only), `fstab`, `group`/`gshadow`/`passwd`/`shadow` (`.add`
     only), `hosts`, `igmpproxy.conf`, `inadyn.conf`, `minidlna.conf`, `mt-daap.service`, `nanorc`
     (no `.add`), `pptpd.conf`, `profile` (`.add` only), `smb.conf`, `snmpd.conf`, `stubby.yml`
     (`.add` only), `stubby-INDEX.yml` (SDN, `.add` only), `torrc`, `vsftpd.conf`, `upnp`,
     `wgclient%d`, `wgserver`, `wgserver_peer`.
   - **This feature is disabled by default** — must be enabled under Administration → System
     (JFFS section) before any override file will be honored. A bugged custom config can lock the
     user out entirely; the only recovery is a factory reset (per `Custom-config-files.md`).

2. **Postconf scripts — `/jffs/scripts/<name>.postconf`**. Run after the firmware generates a
   config but before the service starts on it — use for dynamic values a static `.add` file can't
   express. Use the shipped helper functions rather than hand-rolled `sed`:
   ```sh
   #!/bin/sh
   CONFIG=$1
   source /usr/sbin/helper.sh
   pc_replace "old string" "new string" "$CONFIG"
   pc_insert  "anchor string" "string to insert after anchor" "$CONFIG"
   pc_append  "string to append" "$CONFIG"
   pc_delete  "string within line to delete" "$CONFIG"
   ```
   **These block the boot/service-start sequence.** A postconf script that hangs or fails to exit
   stalls the router at boot, requiring a factory reset to recover — always test the script
   manually via `execute_command` before wiring it into a `.postconf` hook.

3. **User scripts — `/jffs/scripts/` only**, matched by exact filename to a documented trigger.
   Verified trigger names: `services-start`, `services-stop`, `service-event` (blocking; args
   `$1`=event `$2`=target), `service-event-end`, `wan-event` (args `$1`=WAN unit 0/1, `$2`=event
   type: `init`/`connecting`/`connected`/`disconnected`/`stopped`/`disabled`/`stopping`),
   `wan-start` (deprecated since 384.15 — use `wan-event`), `firewall-start` (arg `$1`=WAN
   interface, filter table only), `nat-start` (NAT table only), `init-start` (earliest boot hook,
   right after JFFS mounts), `pre-mount`/`post-mount`/`unmount` (blocking; arg = device or mount
   path), `dhcpc-event` (args `$1`=event type, `$2`=`4`or`6`), `openvpn-event`, `ddns-start`,
   `update-notification`, `qos-start` (blocking), `wgserver-start`/`wgserver-stop`,
   `wgclient-start`/`wgclient-stop` (arg = client unit 1-5).
   - Requirements: must live in `/jffs/scripts/`, start with `#!/sh`/`#!/bin/sh`, be
     `chmod a+rx`, and use **UNIX line endings** (edit via `vi`/`nano` over SSH, or
     `download_file`→edit locally with a UNIX-aware editor→`upload_file`; never a Windows editor).
   - JFFS custom scripts must be enabled first: `nvram set jffs2_scripts=1; nvram commit`
     (also required per-node on AiMesh nodes, run over SSH directly on that node).
   - Debug with `logger` (visible in the webui system log) and a `touch /tmp/<marker>` at the top
     of the script to confirm it actually ran.

4. **Third-party addons — `/jffs/addons/<name>/`**, never files at the addons root. Presence of
   `am_addons` in `nvram get rc_support` gates whether the firmware supports the custom-page
   mechanism at all — check before assuming it. Settings belong in the shared
   `/jffs/addons/custom_settings.txt` store (namespaced keys, alphanumeric/`-`/`_`, ≤29 char
   names, ≤2999 char values, **8KB total repository cap** — do not treat this as bulk storage),
   accessed via `am_settings_get`/`am_settings_set` from `helper.sh`. Never invent a new bare
   NVRAM variable for addon state — new NVRAM variables require a firmware rebuild, and on the
   Broadcom HND platform are additionally capped at 100 bytes.

5. **Entware** (package manager, mutually exclusive with Optware/ASUS DownloadMaster):
   - Requires a USB disk formatted ext2/ext3/ext4 (format via `amtm`'s `fd` option).
   - Installed via `amtm` → `ep` option (or `entware-setup.sh` directly on firmware older than
     384.15 / 384.13_4).
   - Managed via `opkg list` / `opkg install <pkg>` / `opkg remove <pkg>`.
   - **Never assume Entware is installed.** Check first:
     `execute_command("test -x /opt/bin/opkg && echo present || echo absent")` — running
     `opkg`-based commands against a router without Entware just returns "command not found" and
     wastes a round trip.
   - If DownloadMaster was previously installed, its `asusware.*` directory on the USB mount must
     be deleted and the router rebooted before Entware will work correctly.

---

## Section 5 — Hard Safety Guardrails

1. **Reboot requires explicit confirmation.** `reboot_router` takes a `confirm` boolean —
   never pass `true` without the user having explicitly agreed to it in this turn, and always
   state the impact first: *"This will disconnect all clients for roughly 1-2 minutes."* Same
   standard applies to any service restart that's disruptive (`restart_wireless` deauths all WiFi
   clients; `restart_vpnclientN`/`restart_vpnserverN` drops active tunnels).

2. **No firmware flashing, no partition formatting — ever.** These operations are not exposed as
   MCP tools and must stay that way: they're irreversible-in-practice (JFFS contents, including
   scripts, configs, and OpenVPN keys, do **not** reliably survive a firmware flash and must be
   backed up via the webui's "Backup JFFS partition" first), and a failed flash — while
   recoverable via CFE Recovery Mode (power off → hold reset → power on → release at first LED
   blink → 192.168.1.1) — is not something to risk on an unattended action. If a user asks for a
   firmware update or JFFS/USB format, tell them it must be done manually via the router's webui.

3. **`set_nvram_variable` is high-risk — always read-before-write.** Fetch the current value with
   `get_nvram_variable` first, state the diff you're about to make, and warn the user (per
   `Custom-config-files.md` and `User-scripts.md`) that: (a) some variables need `nvram commit` to
   survive a reboot, and separately (b) most variables need the *owning service* restarted before
   the new value takes effect at runtime — `commit` alone does not apply it live. Never batch
   multiple unrelated NVRAM writes into one silent operation; confirm each meaningfully distinct
   change.

4. **Mask secrets in every response you show the user** — the underlying SSH commands return raw
   values, but you must redact before displaying:
   - WiFi PSKs: `wl0_wpa_psk`, `wl1_wpa_psk`, and per-guest-network keys `wl0.1_wpa_psk` /
     `wl0.2_wpa_psk` / `wl0.3_wpa_psk` / `wl1.1_wpa_psk` etc. — show at most the last 4
     characters, e.g. `••••••••wxyz`, never the full passphrase.
   - VPN credentials and key material: OpenVPN/WireGuard private keys, PSKs, and the password
     hash field from `get_vpn_server_users`' `/etc/passwd` read — show usernames/shells, redact
     the hash field entirely.
   - Any NVRAM variable whose name contains `psk`, `pwd`, `password`, `key`, `secret`, or `pass` —
     treat as sensitive by default even if not explicitly listed above.
   - This masking is a display-layer discipline on you, the agent — the tools themselves return
     unredacted data by design (they're operating with the user's own credentials on the user's
     own device), so the responsibility to not echo secrets into chat/logs is yours.

5. **`execute_command` is diagnostics-only, never file-writes.** Its own tool description
   prohibits heredoc/`echo`-based file writes — respect that even under time pressure or when a
   one-liner `sed -i` would be "faster." Use `read_file`/`upload_file`/`download_file` for any
   file mutation, full stop.

6. **Respect the Merlin-only guard on VPN Director tools.** `add_vpn_routing_policy` /
   `remove_vpn_routing_policy` / `list_vpn_policies` refuse to operate on stock ASUS firmware
   (detected via `is_merlin_firmware`) because stock firmware uses an entirely different feature
   (VPN Fusion, `vpnc_dev_policy_list`) with an incompatible file/format. Don't attempt to work
   around that guard by hand-editing `vpndirector_rulelist` via `execute_command`/`upload_file` on
   non-Merlin firmware — it will not be read by stock firmware's VPN Fusion implementation and
   will not do what the user expects.
