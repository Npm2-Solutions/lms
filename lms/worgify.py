# Copyright (c) 2026, NPM2 Solutions Srl and contributors
# License: AGPLv3
"""Worgify Academy — platform mode + feature gating (Design 11).

ONE fork, ONE branch, mode-gated at runtime. The source of truth for the mode is
the ADMIN-ONLY `Worgify Settings` single (System Manager perm only); it falls back
to `site_config.worgify_mode`, then "client". Everything that must differ between
the optisuites-embedded "Training" (client) and the standalone "Worgify Academy"
(hub) reads through here.
"""

import frappe
from frappe import _

CLIENT, HUB = "client", "hub"
_BRAND_DEFAULTS = {CLIENT: "Training", HUB: "Worgify Academy"}

# Per-mode defaults applied when a Worgify Settings feature flag is left unset.
_FEATURE_DEFAULTS = {
	"enable_company_self_signup": {HUB: True, CLIENT: False},
	"enable_marketplace": {HUB: True, CLIENT: False},
	"enable_distribution": {HUB: True, CLIENT: False},
	"enable_stripe_billing": {HUB: True, CLIENT: False},
	"enable_competency": {HUB: False, CLIENT: True},
}


def _settings_value(fieldname):
	"""Read a Worgify Settings field, tolerating the bootstrap window (doctype or
	field not yet migrated) — get_single_value raises on an unknown field."""
	try:
		if frappe.db.exists("DocType", "Worgify Settings"):
			return frappe.db.get_single_value("Worgify Settings", fieldname)
	except Exception:
		return None
	return None


def mode():
	"""Resolve the platform mode: 'client' or 'hub'."""
	m = _settings_value("worgify_mode") or frappe.conf.get("worgify_mode") or CLIENT
	return str(m).strip().lower()


def is_hub():
	return mode() == HUB


def is_client():
	return mode() == CLIENT


def brand_name():
	"""Brand for the current mode, with an admin override (Worgify Settings.brand_name)."""
	return _settings_value("brand_name") or _BRAND_DEFAULTS.get(mode(), "Worgify Academy")


def feature_enabled(flag):
	"""A feature flag from Worgify Settings; when unset, the per-mode default."""
	val = _settings_value(flag)
	if val is None:
		return bool(_FEATURE_DEFAULTS.get(flag, {}).get(mode(), False))
	return bool(val)


def get_user_organization(user=None):
	"""The Learning Organization a user belongs to (via the members child), or None.
	A user belongs to at most one organization. Safe before the doctype exists."""
	user = user or getattr(frappe.session, "user", None)
	if not user or user == "Guest" or not frappe.db.exists("DocType", "Learning Organization"):
		return None
	rows = frappe.get_all(
		"Learning Organization Member", filters={"member": user}, fields=["parent"], limit=1
	)
	return rows[0].parent if rows else None


def is_company_admin_of(organization, user=None):
	"""True if `user` administers `organization` (its admin_user, an Admin member, or
	a System Manager)."""
	user = user or getattr(frappe.session, "user", None)
	if not user or user == "Guest":
		return False
	if "System Manager" in frappe.get_roles(user):
		return True
	# CLIENT (single tenant): a Company Admin manages every organization centrally.
	if is_client() and "Company Admin" in frappe.get_roles(user):
		return True
	if frappe.db.get_value("Learning Organization", organization, "admin_user") == user:
		return True
	return bool(
		frappe.get_all(
			"Learning Organization Member",
			filters={"parent": organization, "member": user, "member_role": "Admin"},
			limit=1,
		)
	)


@frappe.whitelist(allow_guest=True)
def get_mode_context():
	"""SPA bootstrap: mode + brand + resolved feature flags + the caller's org context,
	so the frontend can gate screens/sidebar without extra round-trips."""
	user = getattr(frappe.session, "user", None)
	is_sysmgr = "System Manager" in frappe.get_roles()
	org, is_company_admin = None, False
	if user and user != "Guest" and frappe.db.exists("DocType", "Learning Organization"):
		admin = frappe.get_all("Learning Organization", filters={"admin_user": user}, pluck="name", limit=1)
		if admin:
			org, is_company_admin = admin[0], True
		else:
			org = get_user_organization(user)
			is_company_admin = bool(org) and is_company_admin_of(org, user)
		if is_sysmgr:
			is_company_admin = True
	return {
		"mode": mode(),
		"brand_name": brand_name(),
		"features": {f: feature_enabled(f) for f in _FEATURE_DEFAULTS},
		"can_edit_mode": is_sysmgr,
		"organization": org,
		"is_company_admin": is_company_admin,
	}


@frappe.whitelist()
def set_mode(mode):
	"""Admin-only: flip the platform mode (Client/Hub). Saving runs the controller's
	before_save, which seeds the feature flags to the new mode's defaults."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only an administrator can change the platform mode."), frappe.PermissionError)
	value = (mode or "").strip().capitalize()
	if value not in ("Client", "Hub"):
		frappe.throw(_("Invalid mode."))
	doc = frappe.get_single("Worgify Settings")
	doc.worgify_mode = value
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return get_mode_context()


@frappe.whitelist()
def set_feature(flag, enabled):
	"""Admin-only: toggle a single feature flag."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only an administrator can change features."), frappe.PermissionError)
	if flag not in _FEATURE_DEFAULTS:
		frappe.throw(_("Unknown feature."))
	doc = frappe.get_single("Worgify Settings")
	doc.set(flag, 1 if frappe.parse_json(enabled) else 0)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return get_mode_context()


def ensure_worgify_roles():
	"""after_migrate: create the Worgify role set (idempotent). Website-only roles
	(desk_access=0), like LMS's own. `Company Admin` manages ONE Learning
	Organization's members + group enrollments; the platform admin (us) is plain
	System Manager (the only role allowed to flip the mode)."""
	for role_name in ("Company Admin",):
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role_name, "desk_access": 0}
			).insert(ignore_permissions=True)
