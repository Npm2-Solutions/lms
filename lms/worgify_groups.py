# Copyright (c) 2026, NPM2 Solutions Srl and contributors
# License: AGPLv3
"""Worgify Academy — B2B group layer (Design 11).

Companies are first-class: a `Learning Organization` owns its learners (employees),
enrollment and billing are group-level. ONE fork, mode-gated:

* CLIENT (optisuites): organizations mirror existing `Customer`s and members come
  from the Customer's portal users / `Personnel` — auto-synced, no registration.
* HUB (standalone): companies self-register, employees join by invite or join-code,
  billing is a pool of seats (Stripe).

All optisuites-specific reads are guarded so the module imports/runs on the hub too.
"""

import frappe
from frappe import _
from frappe.utils import random_string

from lms.worgify import is_client, feature_enabled, get_user_organization, is_company_admin_of


# ============================================================================
# Permission scoping — a Company Admin sees ONLY the organization(s) they run
# ============================================================================
def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if not user or user == "Guest":
		return "1=0"
	if "System Manager" in frappe.get_roles(user):
		return ""
	# CLIENT = single tenant -> a Company Admin manages ALL organizations centrally.
	# HUB = multi-tenant -> only the orgs the user administers (tenant isolation).
	if is_client() and "Company Admin" in frappe.get_roles(user):
		return ""
	names = set(frappe.get_all("Learning Organization", filters={"admin_user": user}, pluck="name"))
	names |= set(frappe.get_all(
		"Learning Organization Member",
		filters={"member": user, "member_role": "Admin"}, pluck="parent",
	))
	if not names:
		return "1=0"
	joined = ", ".join(frappe.db.escape(n) for n in names)
	return f"`tabLearning Organization`.name in ({joined})"


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return True
	if is_client() and "Company Admin" in frappe.get_roles(user):
		return True
	name = getattr(doc, "name", doc)
	return is_company_admin_of(name, user)


# ============================================================================
# Join codes / seats
# ============================================================================
def generate_join_code():
	for _i in range(20):
		code = random_string(8).upper()
		if not frappe.db.exists("Learning Organization", {"join_code": code}):
			return code
	return random_string(12).upper()


def compute_seats_used(organization):
	"""A 'seat' = one org member who holds >=1 course enrollment."""
	members = frappe.get_all(
		"Learning Organization Member", filters={"parent": organization}, pluck="member"
	)
	if not members:
		return 0
	enrolled = frappe.get_all(
		"LMS Enrollment", filters={"member": ["in", members]}, pluck="member", distinct=True
	)
	return len(set(enrolled))


def _refresh_seats(organization):
	used = compute_seats_used(organization)
	frappe.db.set_value("Learning Organization", organization, "seats_used", used, update_modified=False)
	return used


def _require_admin(organization):
	if not is_company_admin_of(organization):
		frappe.throw(_("You do not administer this organization."), frappe.PermissionError)


# ============================================================================
# CLIENT auto-provision — mirror optisuites Customers as Learning Organizations
# ============================================================================
def ensure_client_link_fields():
	"""after_migrate (client only): guarded Link fields to optisuites Customer/Personnel.
	No-op on the hub (those doctypes don't exist)."""
	if not frappe.db.exists("DocType", "Customer"):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	fields = {
		"Learning Organization": [
			{"fieldname": "customer", "fieldtype": "Link", "label": "Customer", "options": "Customer",
			 "insert_after": "source", "read_only": 1,
			 "description": "Optisuites Customer this organization mirrors (client mode)."},
		],
	}
	if frappe.db.exists("DocType", "Personnel"):
		fields["Learning Organization Member"] = [
			{"fieldname": "personnel", "fieldtype": "Link", "label": "Personnel", "options": "Personnel",
			 "insert_after": "member", "read_only": 1,
			 "description": "Optisuites Personnel (competency owner) for this learner."},
		]
	create_custom_fields(fields, ignore_validate=True)


def _customer_portal_user_rows(customer):
	"""The (user, enabled) rows of Customer.portal_users, tolerant of the child shape."""
	try:
		doc = frappe.get_doc("Customer", customer)
		rows = []
		for r in (doc.get("portal_users") or []):
			u = r.get("user")
			if not u:
				continue
			enabled = r.get("enabled")
			rows.append((u, True if enabled is None else bool(enabled)))
		return rows
	except Exception:
		return []


def sync_organizations_from_customers():
	"""after_migrate (client only): mirror each optisuites Customer as a Learning
	Organization (idempotent); seed members from the Customer's enabled portal users,
	resolved to Personnel where possible. No-op on the hub."""
	if not is_client() or not frappe.db.exists("DocType", "Customer"):
		return
	ensure_client_link_fields()
	has_personnel = frappe.db.exists("DocType", "Personnel")
	for cust in frappe.get_all("Customer", fields=["name", "customer_name"]):
		org_name = frappe.db.get_value("Learning Organization", {"customer": cust.name}, "name")
		if not org_name:
			org = frappe.new_doc("Learning Organization")
			org.organization_name = cust.customer_name or cust.name
			org.source = "Optisuites Customer"
			org.customer = cust.name
			org.status = "Active"
			org.insert(ignore_permissions=True)
			org_name = org.name
		org = frappe.get_doc("Learning Organization", org_name)
		existing = {m.member for m in org.members}
		changed = False
		for user, enabled in _customer_portal_user_rows(cust.name):
			if not enabled or user in existing:
				continue
			row = org.append("members", {"member": user, "member_role": "Learner", "status": "Active"})
			if has_personnel:
				pers = frappe.db.get_value("Personnel", {"user": user}, "name")
				if pers:
					row.personnel = pers
			changed = True
		if changed:
			org.save(ignore_permissions=True)
	frappe.db.commit()


# ============================================================================
# HUB registration — company self-signup + employee onboarding
# ============================================================================
@frappe.whitelist(allow_guest=True)
def register_company(organization_name, admin_email, admin_full_name, contact_email=None):
	"""Hub: a company self-registers. Creates the Company Admin user + the Learning
	Organization (with a join code) and returns the join code. Feature-gated."""
	if not feature_enabled("enable_company_self_signup"):
		frappe.throw(_("Company self-registration is not enabled."))
	organization_name = (organization_name or "").strip()
	admin_email = (admin_email or "").strip().lower()
	if not organization_name or not admin_email or not admin_full_name:
		frappe.throw(_("Organization name, admin name and admin email are required."))

	# admin user
	if frappe.db.exists("User", admin_email):
		user = frappe.get_doc("User", admin_email)
	else:
		user = frappe.get_doc({
			"doctype": "User", "email": admin_email, "first_name": admin_full_name.strip(),
			"user_type": "Website User", "send_welcome_email": 1,
		}).insert(ignore_permissions=True)
	for role in ("Company Admin", "LMS Student"):
		if frappe.db.exists("Role", role) and role not in (r.role for r in user.roles):
			user.add_roles(role)

	org = frappe.get_doc({
		"doctype": "Learning Organization", "organization_name": organization_name,
		"source": "Self-Registered", "status": "Active", "admin_user": user.name,
		"contact_email": (contact_email or admin_email),
		"members": [{"member": user.name, "member_role": "Admin", "status": "Active"}],
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return {"organization": org.name, "join_code": org.join_code}


@frappe.whitelist()
def invite_employee(organization, email, full_name=None, member_role="Learner"):
	"""Company Admin: add/invite an employee. Creates a Website User (LMS Student) if
	needed and adds them as a member (status Invited)."""
	_require_admin(organization)
	email = (email or "").strip().lower()
	if not email:
		frappe.throw(_("Email is required."))
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": (full_name or email).strip(),
			"user_type": "Website User", "send_welcome_email": 1,
		}).insert(ignore_permissions=True)
	if frappe.db.exists("Role", "LMS Student") and "LMS Student" not in (r.role for r in user.roles):
		user.add_roles("LMS Student")

	org = frappe.get_doc("Learning Organization", organization)
	if any(m.member == user.name for m in org.members):
		return {"organization": organization, "member": user.name, "status": "already_member"}
	org.append("members", {"member": user.name, "member_role": member_role, "status": "Invited"})
	org.save(ignore_permissions=True)
	frappe.db.commit()
	return {"organization": organization, "member": user.name, "status": "Invited"}


@frappe.whitelist()
def set_member_role(organization, member, role):
	"""Company Admin: change a member's role within the organization (Learner/Admin).
	An Admin member co-manages the org (same scoping as the admin_user)."""
	_require_admin(organization)
	if role not in ("Learner", "Admin"):
		frappe.throw(_("Invalid member role."))
	org = frappe.get_doc("Learning Organization", organization)
	row = next((m for m in org.members if m.member == member), None)
	if not row:
		frappe.throw(_("Member not found in this organization."))
	row.member_role = role
	org.save(ignore_permissions=True)
	frappe.db.commit()
	return {"organization": organization, "member": member, "member_role": role}


@frappe.whitelist()
def join_with_code(join_code):
	"""A logged-in user joins their company using its join code (hub self-onboarding)."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please sign in first."), frappe.PermissionError)
	org_name = frappe.db.get_value("Learning Organization", {"join_code": (join_code or "").strip().upper()}, "name")
	if not org_name:
		frappe.throw(_("Invalid join code."))
	org = frappe.get_doc("Learning Organization", org_name)
	if any(m.member == user for m in org.members):
		return {"organization": org_name, "status": "already_member"}
	org.append("members", {"member": user, "member_role": "Learner", "status": "Active"})
	org.save(ignore_permissions=True)
	frappe.db.commit()
	return {"organization": org_name, "status": "joined"}


# ============================================================================
# Group enrollment
# ============================================================================
@frappe.whitelist()
def enroll_members(organization, course, members=None):
	"""Company Admin: bulk-enroll members in a course. CLIENT internal training enrols the
	given Personnel users directly (no seat pool); HUB/B2B enrols Learning Organization
	members honouring the seat pool (max_seats; 0 = unlimited)."""
	if not frappe.db.exists("LMS Course", course):
		frappe.throw(_("Course not found."))
	if isinstance(members, str):
		members = frappe.parse_json(members)
	# CLIENT internal: the "organization" is the company; members are Personnel users.
	if is_client() and frappe.db.exists("DocType", "Personnel") and not frappe.db.exists("Learning Organization", organization):
		if not ({"System Manager", "Company Admin"} & set(frappe.get_roles())):
			frappe.throw(_("Not permitted."), frappe.PermissionError)
		if not members:
			members = [p.user for p in frappe.get_all("Personnel", {"user": ["is", "set"]}, ["user"]) if p.user]
		enrolled, already = [], []
		for user in [m for m in members if frappe.db.exists("User", m)]:
			if frappe.db.exists("LMS Enrollment", {"member": user, "course": course}):
				already.append(user)
				continue
			frappe.get_doc({"doctype": "LMS Enrollment", "member": user, "course": course}).insert(
				ignore_permissions=True
			)
			enrolled.append(user)
		frappe.db.commit()
		return {"enrolled": enrolled, "already_enrolled": already, "blocked_no_seats": [],
		        "seats_used": None, "max_seats": None}
	# HUB / B2B: Learning Organization with a seat pool.
	_require_admin(organization)
	org = frappe.get_doc("Learning Organization", organization)
	if not members:
		members = [m.member for m in org.members if m.status == "Active"]

	max_seats = int(org.max_seats or 0)
	seated = set(frappe.get_all(
		"LMS Enrollment",
		filters={"member": ["in", [m.member for m in org.members] or [""]]},
		pluck="member", distinct=True,
	))
	enrolled, already, blocked = [], [], []
	for user in members:
		if frappe.db.exists("LMS Enrollment", {"member": user, "course": course}):
			already.append(user)
			continue
		if max_seats and user not in seated and len(seated) >= max_seats:
			blocked.append(user)
			continue
		frappe.get_doc({"doctype": "LMS Enrollment", "member": user, "course": course}).insert(
			ignore_permissions=True
		)
		seated.add(user)
		enrolled.append(user)
	_refresh_seats(organization)
	frappe.db.commit()
	return {
		"enrolled": enrolled, "already_enrolled": already, "blocked_no_seats": blocked,
		"seats_used": len(seated), "max_seats": max_seats,
	}


def _internal_workforce():
	"""CLIENT internal-training lens: the company IS the organization and its members ARE
	the optisuites `Personnel` (the workforce) — the SAME population the Competency overview
	shows. No join codes, no seat pool (you own the platform). Admins see the full roster."""
	roles = set(frappe.get_roles())
	can_admin = bool({"System Manager", "Company Admin"} & roles)
	company = (frappe.defaults.get_global_default("company")
	           or frappe.db.get_value("Company", {}, "name")
	           or _("My organization"))
	people = frappe.get_all("Personnel", fields=["name", "full_name", "user"], order_by="full_name asc")
	members = [{
		"member": p.user or p.name,
		"personnel": p.name,
		"full_name": p.full_name or p.name,
		"member_role": "Member",
		"status": "Active" if p.user else "No LMS login",
		"has_login": bool(p.user),
	} for p in people]
	return {
		"organization": company, "organization_name": company, "status": "Active",
		"is_admin": can_admin, "is_internal": True,
		"join_code": None, "max_seats": None, "seats_used": len(members),
		"members": members if can_admin else [],
	}


@frappe.whitelist()
def get_my_organization():
	"""SPA 'My Organization'. CLIENT = internal training: the company + its Personnel
	workforce (matches the Competency overview). HUB / B2B = the Learning Organization the
	user administers or belongs to, with members + seat usage."""
	# Internal-training lens (client + optisuites Personnel): one coherent population.
	if is_client() and frappe.db.exists("DocType", "Personnel"):
		return _internal_workforce()
	user = frappe.session.user
	org_name = None
	admin = frappe.get_all("Learning Organization", filters={"admin_user": user}, pluck="name", limit=1)
	if admin:
		org_name = admin[0]
	else:
		org_name = get_user_organization(user)
	if not org_name:
		return {"organization": None}
	org = frappe.get_doc("Learning Organization", org_name)
	can_admin = is_company_admin_of(org_name, user)
	return {
		"organization": org.name,
		"organization_name": org.organization_name,
		"status": org.status,
		"is_admin": can_admin,
		"join_code": org.join_code if can_admin else None,
		"max_seats": org.max_seats,
		"seats_used": _refresh_seats(org_name),
		"members": [
			{"member": m.member, "full_name": m.full_name, "member_role": m.member_role, "status": m.status}
			for m in org.members
		] if can_admin else [],
	}
