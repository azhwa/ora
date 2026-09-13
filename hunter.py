#!/usr/bin/env python3
"""
Oracle ARM (A1) Always Free Instance Hunter
Lightweight, resilient daemon designed to run 24/7 on Linux / VPS Micro.
Features smart retry, AD rotation, and Telegram notifications.
"""

import argparse
import datetime
import json
import logging
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import oci
from telegram_notify import (
    TelegramBotListener,
    notify_abort,
    notify_heartbeat,
    notify_startup,
    notify_success,
    send_telegram_message,
)

# Configure UTF-8 stdout for emoji support across Windows and Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Logging Setup
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("oracle_hunter.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("hunter")


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Loads application configuration from JSON."""
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at: {config_path}")
        logger.info("Please copy config.json.example to config.json and fill in your details.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {config_path}: {e}")
            sys.exit(1)


def get_oci_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Builds OCI SDK configuration dictionary from config.json or ~/.oci/config."""
    # Option 1: Inline credentials in config.json
    key_candidates = [
        os.path.expanduser(cfg.get("key_file_path", "")),
        os.path.expanduser("~/.oci/oci_api_key.pem"),
        os.path.abspath("oci_api_key.pem"),
    ]
    resolved_key = None
    for k in key_candidates:
        if k and os.path.exists(k):
            resolved_key = k
            break

    if resolved_key and cfg.get("user_ocid") and cfg.get("tenancy_ocid") and cfg.get("fingerprint"):
        return {
            "user": cfg["user_ocid"],
            "fingerprint": cfg["fingerprint"],
            "key_file": resolved_key,
            "tenancy": cfg["tenancy_ocid"],
            "region": cfg.get("region", "ap-mumbai-1"),
        }

    # Option 2: Fall back to standard ~/.oci/config file
    oci_config_file = os.path.expanduser(cfg.get("oci_config_file", "~/.oci/config"))
    if os.path.exists(oci_config_file):
        profile = cfg.get("oci_profile", "DEFAULT")
        return oci.config.from_file(file_location=oci_config_file, profile_name=profile)

    expected_path = os.path.expanduser(cfg.get("key_file_path", "~/.oci/oci_api_key.pem"))
    if not resolved_key:
        raise FileNotFoundError(
            f"API Private Key file not found at: '{expected_path}'. "
            "Please upload your 'oci_api_key.pem' to ~/.oci/ or the project folder on this VPS."
        )

    raise ValueError(
        "Could not find valid OCI credentials. Please specify user_ocid, tenancy_ocid, "
        "fingerprint, and key_file_path in config.json or configure ~/.oci/config."
    )


def resolve_ssh_keys(cfg: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Resolves and prepares all SSH public keys that will be injected into the instance.
    Guarantees that the user will NEVER be locked out by:
    1. Including all keys specified in cfg['ssh_authorized_keys'] (e.g. user's Laptop/PC key).
    2. Including the local host key (from pub path, ~/.ssh/oraclehost_id_rsa, ~/.ssh/id_rsa, or newly auto-generated).
    3. Returning the combined newline-separated authorized_keys string along with the local key paths.
    """
    keys_list: List[str] = []

    # 1. Configured authorized keys (strings or list)
    configured_keys = cfg.get("ssh_authorized_keys", [])
    if isinstance(configured_keys, str):
        configured_keys = [k.strip() for k in configured_keys.splitlines() if k.strip()]
    for k in configured_keys:
        clean = k.strip()
        if (clean.startswith("ssh-rsa") or clean.startswith("ssh-ed25519") or clean.startswith("ecdsa-")) and clean not in keys_list:
            keys_list.append(clean)

    # 2. Local machine key resolution
    pub_candidates = [
        os.path.expanduser(cfg.get("ssh_public_key_path", "~/.ssh/id_rsa.pub")),
        os.path.expanduser("~/.ssh/oraclehost_id_rsa.pub"),
        os.path.expanduser("~/.ssh/id_rsa.pub"),
    ]
    priv_candidates = [
        os.path.expanduser(cfg.get("ssh_private_key_path", "~/.ssh/id_rsa")),
        os.path.expanduser("~/.ssh/oraclehost_id_rsa"),
        os.path.expanduser("~/.ssh/id_rsa"),
    ]

    resolved_pub = None
    resolved_priv = None

    for pub, priv in zip(pub_candidates, priv_candidates):
        if os.path.exists(pub) and os.path.exists(priv):
            try:
                with open(pub, "r", encoding="utf-8") as f:
                    local_key = f.read().strip()
                if local_key.startswith("ssh-rsa") or local_key.startswith("ssh-ed25519"):
                    resolved_pub = pub
                    resolved_priv = priv
                    if local_key not in keys_list:
                        keys_list.append(local_key)
                    break
            except Exception:
                pass

    # 3. If no local key pair exists on the machine running the bot, auto-generate one
    if not resolved_pub or not resolved_priv:
        target_priv = os.path.expanduser(cfg.get("ssh_private_key_path") or "~/.ssh/oracle_hunter_key")
        if target_priv.endswith(".pub"):
            target_priv = target_priv[:-4]
        target_pub = target_priv + ".pub"

        target_dir = os.path.dirname(target_priv)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        logger.info(f"🔑 Local SSH key not found on this machine. Generating new RSA 2048 key pair at: {target_priv}...")
        cmd = f'ssh-keygen -t rsa -b 2048 -f "{target_priv}" -N "" -q'
        ret = os.system(cmd)
        if ret != 0:
            if not keys_list:
                raise RuntimeError(f"Failed to generate SSH key pair using ssh-keygen (exit code {ret}) and no other keys provided.")
            logger.warning(f"ssh-keygen failed (code {ret}), but found {len(keys_list)} key(s) in ssh_authorized_keys.")
            return "\n".join(keys_list), "", ""

        try:
            os.chmod(target_priv, 0o600)
        except Exception:
            pass

        with open(target_pub, "r", encoding="utf-8") as f:
            new_key = f.read().strip()

        if new_key not in keys_list:
            keys_list.append(new_key)

        resolved_pub = target_pub
        resolved_priv = target_priv
        logger.info(f"✅ Automatically generated new SSH key pair: {target_pub}")

    combined_keys = "\n".join(keys_list)
    return combined_keys, resolved_pub or "", resolved_priv or ""


def get_availability_domains(identity_client: oci.identity.IdentityClient, compartment_id: str) -> List[str]:
    """Retrieves list of availability domain names."""
    response = identity_client.list_availability_domains(compartment_id=compartment_id)
    return [ad.name for ad in response.data]


def find_image(
    compute_client: oci.core.ComputeClient,
    compartment_id: str,
    shape: str,
    operating_system: str,
    os_version: str,
) -> oci.core.models.Image:
    """Finds matching OS image compatible with the shape."""
    # OCI uses 'Canonical Ubuntu' for Ubuntu
    os_name = "Canonical Ubuntu" if "ubuntu" in operating_system.lower() else operating_system

    images = compute_client.list_images(
        compartment_id=compartment_id,
        operating_system=os_name,
        shape=shape,
        sort_by="TIMECREATED",
        sort_order="DESC",
    ).data

    if not images:
        # Fallback query with original string
        images = compute_client.list_images(
            compartment_id=compartment_id,
            operating_system=operating_system,
            shape=shape,
            sort_by="TIMECREATED",
            sort_order="DESC",
        ).data

    if not images:
        raise RuntimeError(f"No {operating_system} images found for shape {shape}")

    # Prioritize non-minimal images matching the desired version
    filtered = [img for img in images if os_version.lower() in (img.display_name or "").lower()]
    standard = [img for img in filtered if "minimal" not in (img.display_name or "").lower()]

    selected = (standard or filtered or images)[0]
    return selected


def get_public_ip(
    compute_client: oci.core.ComputeClient,
    network_client: oci.core.VirtualNetworkClient,
    compartment_id: str,
    instance_id: str,
) -> Optional[str]:
    """Resolves the assigned public IP for an instance."""
    try:
        attachments = compute_client.list_vnic_attachments(
            compartment_id=compartment_id,
            instance_id=instance_id,
        ).data
        for att in attachments:
            if att.vnic_id:
                vnic = network_client.get_vnic(vnic_id=att.vnic_id).data
                if vnic.public_ip:
                    return vnic.public_ip
    except Exception as e:
        logger.warning(f"Could not resolve public IP: {e}")
    return None


def wait_for_running(
    compute_client: oci.core.ComputeClient,
    instance_id: str,
    timeout_minutes: int = 15,
) -> bool:
    """Polls instance status until it reaches RUNNING."""
    deadline = datetime.datetime.utcnow() + datetime.timedelta(minutes=timeout_minutes)
    while datetime.datetime.utcnow() < deadline:
        try:
            inst = compute_client.get_instance(instance_id=instance_id).data
            state = inst.lifecycle_state
            logger.info(f"Instance lifecycle state: {state}")
            if state == "RUNNING":
                return True
            if state in ["TERMINATED", "FAILED"]:
                return False
        except Exception as e:
            logger.warning(f"Error querying instance status: {e}")
        time.sleep(10)
    return False


def run_preflight(
    cfg: Dict[str, Any],
    compute_client: oci.core.ComputeClient,
    identity_client: oci.identity.IdentityClient,
    network_client: oci.core.VirtualNetworkClient,
) -> bool:
    """Runs preflight validation checks."""
    logger.info("=== Running Preflight Check ===")
    compartment_id = cfg["compartment_ocid"]
    shape = cfg.get("shape", "VM.Standard.A1.Flex")
    os_name = cfg.get("operating_system", "Canonical Ubuntu")
    os_version = cfg.get("os_version", "24.04")

    # 1. ADs
    ads = get_availability_domains(identity_client, cfg["tenancy_ocid"])
    logger.info(f"Availability Domains ({len(ads)}): {', '.join(ads)}")

    # 2. Image
    img = find_image(compute_client, compartment_id, shape, os_name, os_version)
    logger.info(f"Selected Image: {img.display_name} (ID: {img.id})")

    # 3. Existing instances
    instances = compute_client.list_instances(compartment_id=compartment_id).data
    existing_a1 = [
        i for i in instances
        if i.shape == shape and i.lifecycle_state not in ["TERMINATED", "TERMINATING"]
    ]
    if existing_a1:
        logger.warning(f"Found {len(existing_a1)} existing {shape} instance(s):")
        for i in existing_a1:
            logger.warning(f" - {i.display_name} ({i.id})")
        if not cfg.get("allow_existing", False):
            logger.error("Preflight aborted: allow_existing is false and existing A1 instances exist.")
            return False
    else:
        logger.info("No existing A1 instances found. Ready to hunt.")

    # 4. SSH Keys Check (Guarantees user access)
    ssh_keys, pub_path, priv_path = resolve_ssh_keys(cfg)
    key_count = len([k for k in ssh_keys.splitlines() if k.strip()])
    logger.info(f"SSH Keys: {key_count} authorized public key(s) will be injected into the VM.")
    if pub_path:
        logger.info(f"Local key pair: {pub_path} / {priv_path}")

    # 5. Network & Port 22 (SSH) Ingress Rule Check
    subnet_id = cfg.get("subnet_ocid")
    if subnet_id:
        try:
            subnet = network_client.get_subnet(subnet_id).data
            logger.info(f"Subnet verified: {subnet.display_name} ({subnet.cidr_block})")
            port_22_open = False
            for sec_id in subnet.security_list_ids:
                sec_list = network_client.get_security_list(sec_id).data
                for rule in sec_list.ingress_security_rules:
                    if rule.protocol == "6":  # TCP
                        tcp_opts = rule.tcp_options
                        if not tcp_opts or not tcp_opts.destination_port_range:
                            port_22_open = True
                            break
                        dp = tcp_opts.destination_port_range
                        if dp.min <= 22 <= dp.max:
                            port_22_open = True
                            break
                if port_22_open:
                    break
            if port_22_open:
                logger.info("Security List Check: Port 22 (SSH) Ingress is OPEN. SSH login will succeed.")
            else:
                logger.warning("WARNING: Port 22 (SSH) Ingress rule was NOT detected in subnet Security Lists! Ensure Port 22 is open.")
        except Exception as e:
            logger.warning(f"Could not verify subnet security list: {e}")

    logger.info("=== Preflight PASSED! Everything looks good ===")
    return True


def hunt(cfg: Dict[str, Any], dry_run: bool = False, once: bool = False) -> None:
    """Main instance hunting loop."""
    oci_cfg = get_oci_config(cfg)
    compute_client = oci.core.ComputeClient(oci_cfg)
    identity_client = oci.identity.IdentityClient(oci_cfg)
    network_client = oci.core.VirtualNetworkClient(oci_cfg)

    # Preflight Check
    if not run_preflight(cfg, compute_client, identity_client, network_client):
        sys.exit(1)

    if dry_run:
        logger.info("Dry-run requested. Exiting without launching instance.")
        return

    # Telegram Credentials
    tg_token = cfg.get("telegram_bot_token", "")
    tg_chat_id = cfg.get("telegram_chat_id", "")
    notify_startup(tg_token, tg_chat_id, cfg)

    # Launch Parameters
    compartment_id = cfg["compartment_ocid"]
    subnet_id = cfg["subnet_ocid"]
    shape = cfg.get("shape", "VM.Standard.A1.Flex")
    ocpus = int(cfg.get("ocpus", 1))
    memory_gb = int(cfg.get("memory_in_gbs", 4))
    boot_volume_gb = int(cfg.get("boot_volume_size_gb", 50))
    display_name = cfg.get("display_name", "free-tier-arm")
    min_interval = int(cfg.get("min_interval_seconds", 30))
    max_interval = int(cfg.get("max_interval_seconds", 60))
    ssh_keys, pub_path, priv_path = resolve_ssh_keys(cfg)
    ssh_user = "ubuntu" if "ubuntu" in cfg.get("operating_system", "").lower() else "opc"
    ssh_key_path = priv_path

    # Find Image
    img = find_image(
        compute_client,
        compartment_id,
        shape,
        cfg.get("operating_system", "Canonical Ubuntu"),
        cfg.get("os_version", "24.04"),
    )

    # ADs to rotate
    ads = get_availability_domains(identity_client, cfg["tenancy_ocid"])
    configured_ad = cfg.get("availability_domain")
    if configured_ad and configured_ad.lower() != "all":
        ads = [ad for ad in ads if configured_ad.lower() in ad.lower()]

    logger.info(f"Targeting ADs: {', '.join(ads)}")
    logger.info(f"Specifications: {ocpus} OCPU / {memory_gb} GB RAM / {boot_volume_gb} GB Boot Volume")

    attempts = 0
    capacity_hits = 0
    start_time = datetime.datetime.utcnow()
    heartbeat_interval = int(cfg.get("heartbeat_attempts", 300))

    hunter_state = {
        "paused": False,
        "attempts": 0,
        "capacity_hits": 0,
        "current_ad": ads[0] if ads else "",
        "start_time": start_time,
    }

    # Start Telegram interactive command listener (allows /status, /stop, /start, /exit)
    listener = TelegramBotListener(tg_token, tg_chat_id, hunter_state, cfg)
    listener.start()

    while True:
        if hunter_state.get("paused"):
            time.sleep(1)
            continue

        attempts += 1
        hunter_state["attempts"] = attempts
        ad = ads[(attempts - 1) % len(ads)]
        hunter_state["current_ad"] = ad
        logger.info(f"[Attempt #{attempts}] Requesting instance in {ad}...")

        launch_details = oci.core.models.LaunchInstanceDetails(
            availability_domain=ad,
            compartment_id=compartment_id,
            display_name=display_name,
            shape=shape,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=ocpus,
                memory_in_gbs=memory_gb,
            ),
            source_details=oci.core.models.InstanceSourceViaImageDetails(
                image_id=img.id,
                boot_volume_size_in_gbs=boot_volume_gb,
            ),
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=subnet_id,
                assign_public_ip=True,
            ),
            metadata={"ssh_authorized_keys": ssh_keys},
        )

        try:
            response = compute_client.launch_instance(launch_instance_details=launch_details)
            instance = response.data
            logger.info(f"🎉 INSTANCE CREATED! ID: {instance.id}")
            logger.info("Waiting for instance to reach RUNNING state...")

            running = wait_for_running(compute_client, instance.id)
            public_ip = (
                get_public_ip(compute_client, network_client, compartment_id, instance.id)
                if running
                else None
            )

            logger.info(f"✅ SUCCESS! Public IP: {public_ip or 'Pending'}")
            notify_success(
                tg_token,
                tg_chat_id,
                instance.id,
                public_ip,
                shape,
                ocpus,
                memory_gb,
                ssh_user,
                ssh_key_path,
                cfg.get("local_pc_key_name", "oraclehost_id_rsa"),
            )
            logger.info("Instance created successfully! Stopping daemon in PM2...")
            os.system("pm2 stop oracle-hunter 2>/dev/null || true")
            sys.exit(0)

        except oci.exceptions.ServiceError as e:
            code = e.code or ""
            status = e.status or 0
            message = e.message or ""

            # Check fatal errors
            if code in ["LimitExceeded", "NotAuthorizedOrNotFound", "AuthFailure", "InvalidParameter"]:
                logger.error(f"Fatal error ({code}): {message}")
                notify_abort(tg_token, tg_chat_id, f"Fatal error ({code}): {message}")
                os.system("pm2 stop oracle-hunter 2>/dev/null || true")
                sys.exit(1)

            # Capacity / Transient error (Safe to retry)
            capacity_hits += 1
            hunter_state["capacity_hits"] = capacity_hits
            logger.warning(f"Capacity unavailable or transient error ({code} / {status}): {message}")

        except Exception as e:
            logger.warning(f"Unexpected network or client exception: {e}")

        if once:
            logger.info("Single attempt completed. Exiting.")
            return

        # Periodic Heartbeat
        if attempts % heartbeat_interval == 0:
            elapsed = datetime.datetime.utcnow() - start_time
            elapsed_str = str(datetime.timedelta(seconds=int(elapsed.total_seconds())))
            notify_heartbeat(tg_token, tg_chat_id, attempts, capacity_hits, ad, elapsed_str)

        # Sleep before next retry in 1s slices to respond immediately if /stop is sent
        delay = random.randint(min_interval, max_interval)
        logger.info(f"Retrying in {delay}s...")
        for _ in range(delay):
            if hunter_state.get("paused"):
                break
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Oracle Always Free ARM Instance Hunter")
    parser.add_argument("-c", "--config", default="config.json", help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Validate credentials and exit")
    parser.add_argument("--preflight", action="store_true", help="Run preflight check and exit")
    parser.add_argument("--once", action="store_true", help="Try launch only once and exit")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test message to Telegram")

    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.test_telegram:
        token = cfg.get("telegram_bot_token", "")
        chat_id = cfg.get("telegram_chat_id", "")
        if not token or not chat_id:
            logger.error("telegram_bot_token or telegram_chat_id not set in config.json")
            sys.exit(1)
        logger.info("Sending test message to Telegram...")
        ok = send_telegram_message(token, chat_id, "🔔 <b>Test Notification from Oracle ARM Hunter!</b>")
        if ok:
            logger.info("✅ Telegram test message sent successfully!")
        else:
            logger.error("❌ Failed to send Telegram message. Please check your token and chat_id.")
        return

    hunt(cfg, dry_run=args.dry_run or args.preflight, once=args.once)


if __name__ == "__main__":
    main()
