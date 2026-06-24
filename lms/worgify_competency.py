# Copyright (c) 2026, NPM2 Solutions Srl and contributors
# License: AGPLv3
"""Worgify Academy — competency bridge (Design 11), folded INTO the fork.

ONE branch, mode-gated: this bridge is active on a CLIENT bench (optisuites present)
and INERT on the HUB (no optisuites) via guarded imports — never two branches.

It surfaces LMS training certificates as competency evidence into the optisuites
Person-360 and the recordbook dossier (MRB), mapping the LMS member (User) -> the
canonical Personnel. No separate Personnel-linked doctype is shipped (that would
break the hub); we add a guarded `personnel` Custom Field to LMS Certificate only
where Personnel exists.
"""

import frappe


def _personnel_for_user(user):
	"""Map an LMS member (User) -> Personnel, or None. Guarded: returns None when
	optisuites is absent (the hub) so nothing breaks."""
	if not user or user == "Guest":
		return None
	try:
		from optisuites.personnel.api import get_personnel_for_user
	except ImportError:
		return None
	return get_personnel_for_user(user)


def ensure_competency_fields():
	"""after_migrate hook: add the `personnel` link to LMS Certificate, but ONLY on a
	bench that has optisuites (Personnel). No-op on the hub, so the fork stays
	standalone-deployable."""
	if not frappe.db.exists("DocType", "Personnel"):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"LMS Certificate": [
				{
					"fieldname": "personnel",
					"fieldtype": "Link",
					"label": "Personnel",
					"options": "Personnel",
					"insert_after": "member",
					"read_only": 1,
					"description": "Competency owner (optisuites Personnel), stamped from the LMS member.",
				}
			]
		},
		ignore_validate=True,
	)


def on_lms_certificate(doc, method=None):
	"""doc_events LMS Certificate.after_insert: stamp the competency owner (Personnel)
	from the member. Fail-soft — never break certificate issuance."""
	try:
		if not doc.meta.has_field("personnel") or doc.get("personnel"):
			return
		personnel = _personnel_for_user(doc.get("member"))
		if personnel:
			doc.db_set("personnel", personnel, update_modified=False)
	except Exception:
		frappe.log_error(
			title="worgify: LMS Certificate personnel stamp failed",
			message=frappe.get_traceback(),
		)


# --- recordbook MRB contributor: the Personnel Training & Competency register -----
# (Zero recordbook imports at module scope — recordbook discovers this via the
# record_book_contributors hook and calls build() with the plain-dict contract.)


def _esc(v):
	return frappe.utils.escape_html("" if v is None else str(v))


def _fmtdate(v):
	return frappe.utils.formatdate(v) if v else ""


def _reg_row(who, item, source, issued, expiry):
	return (
		"<tr>"
		f"<td>{_esc(who)}</td><td>{_esc(item)}</td><td>{_esc(source)}</td>"
		f"<td>{_esc(_fmtdate(issued))}</td><td>{_esc(_fmtdate(expiry))}</td>"
		"</tr>"
	)


def build_training_register(book, scope, section_row=None) -> dict:
	"""Org-wide personnel competency register: internal LMS certificates AND external
	training records, in one table with a Source column. Personnel-level (not
	project-bound) — the whole register regardless of scope, like a welder
	qualification register in an MRB."""
	internal, external = [], []
	if frappe.db.exists("DocType", "LMS Certificate"):
		fields = ["member", "member_name", "course", "course_title", "issue_date", "expiry_date"]
		if frappe.get_meta("LMS Certificate").has_field("personnel"):
			fields.append("personnel")
		internal = frappe.get_all("LMS Certificate", fields=fields, order_by="member_name asc, issue_date desc")
	if frappe.db.exists("DocType", "External Training Record"):
		external = frappe.get_all(
			"External Training Record",
			fields=["personnel", "title", "issuing_body", "issue_date", "expiry_date"],
			order_by="issue_date desc",
		)
	if not internal and not external:
		return {"metadata": {"empty": True, "warnings": [
			{"severity": "info", "code": "empty", "message": "No training on record."}]}}
	names = {}
	pers_ids = list({e.get("personnel") for e in external if e.get("personnel")})
	if pers_ids and frappe.db.exists("DocType", "Personnel"):
		for p in frappe.get_all("Personnel", filters={"name": ["in", pers_ids]}, fields=["name", "full_name"]):
			names[p.name] = p.full_name or p.name
	rows = []
	for c in internal:
		who = c.get("member_name") or c.get("personnel") or c.get("member")
		rows.append(_reg_row(who, c.get("course_title") or c.get("course"), "Internal", c.get("issue_date"), c.get("expiry_date")))
	for e in external:
		who = names.get(e.get("personnel"), e.get("personnel"))
		item = e.get("title")
		if e.get("issuing_body"):
			item = f"{item} — {e.get('issuing_body')}"
		rows.append(_reg_row(who, item, "External", e.get("issue_date"), e.get("expiry_date")))
	html = (
		"<div class='print-heading'><h2><div>Personnel Training &amp; Competency</div>"
		f"<small class='sub-heading'>{len(internal)} internal · {len(external)} external · organisation-wide</small></h2></div>"
		"<table class='table table-bordered mrb-tight'><thead><tr>"
		"<th>Personnel</th><th>Training</th><th>Source</th><th>Issued</th><th>Expiry</th>"
		"</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
	)
	return {
		"html": html,
		"metadata": {
			"empty": False,
			"warnings": [],
			"snapshot": {"internal": [dict(c) for c in internal], "external": [dict(e) for e in external]},
			"builder_version": "1.1",
			"estimated_pages": max(1, (len(internal) + len(external)) // 25 + 1),
		},
	}


# ============================================================================
# G5 — auto-issue the competency certificate on self-paced completion.
# Only courses flagged `grants_training_certificate` mint evidence (so the LMS
# demo course never produces spurious certs). The after_insert hook above
# (on_lms_certificate) then stamps the Personnel and surfaces it (Person-360 + MRB).
# ============================================================================
GRANTS_FIELD = "grants_training_certificate"


def _course_grants_cert(course):
	if not course or not frappe.get_meta("LMS Course").has_field(GRANTS_FIELD):
		return False
	return bool(frappe.db.get_value("LMS Course", course, GRANTS_FIELD))


def _certificate_template():
	pfs = frappe.get_all(
		"Print Format", filters={"doc_type": "LMS Certificate"}, pluck="name", limit_page_length=1
	)
	return pfs[0] if pfs else None


def issue_completion_certificate(course, member):
	"""Idempotent + self-gating: issue an LMS Certificate for a completed,
	competency-bearing course. Returns the cert name (existing or new) or None."""
	if not course or not member or not _course_grants_cert(course):
		return None
	existing = frappe.db.get_value("LMS Certificate", {"member": member, "course": course}, "name")
	if existing:
		return existing
	template = _certificate_template()
	if not template:
		return None
	cert = frappe.new_doc("LMS Certificate")
	cert.member = member
	cert.course = course
	cert.template = template
	today = frappe.utils.nowdate()
	if cert.meta.has_field("issue_date"):
		cert.issue_date = today
	# Competency validity: the course's certificate_validity_months drives expiry
	# (0/empty = no expiry, e.g. a one-off induction). Surfaced in Person-360 + MRB.
	validity = frappe.db.get_value("LMS Course", course, "certificate_validity_months")
	if validity and cert.meta.has_field("expiry_date"):
		cert.expiry_date = frappe.utils.add_months(today, int(validity))
	cert.insert(ignore_permissions=True)  # after_insert -> on_lms_certificate stamps Personnel
	return cert.name


def on_course_progress(doc, method=None):
	"""LMS Course Progress.on_update: issue the certificate on the 100% transition
	for a competency-bearing course. Fail-soft — never break the learner's save."""
	try:
		course, member = doc.get("course"), doc.get("member")
		if not course or not member or not _course_grants_cert(course):
			return
		from lms.lms.utils import get_course_progress

		if get_course_progress(course, member) < 100:
			return
		issue_completion_certificate(course, member)
	except Exception:
		frappe.log_error(
			title="worgify: completion certificate issuance failed",
			message=frappe.get_traceback(),
		)


def reconcile_completions():
	"""Daily safety net: issue certificates for completed, competency-bearing
	enrolments that still lack one (covers the db.set_value progress bypass / imports)."""
	if not frappe.db.exists("DocType", "LMS Course") or not frappe.get_meta("LMS Course").has_field(GRANTS_FIELD):
		return
	courses = frappe.get_all("LMS Course", filters={GRANTS_FIELD: 1}, pluck="name")
	if not courses:
		return
	for row in frappe.get_all(
		"LMS Enrollment",
		filters={"course": ["in", courses], "progress": [">=", 100]},
		fields=["course", "member"],
	):
		try:
			issue_completion_certificate(row.course, row.member)
		except Exception:
			frappe.log_error(
				title=f"worgify: reconcile issuance failed ({row.member} / {row.course})",
				message=frappe.get_traceback(),
			)


# ============================================================================
# #2 — Management competency overview / gap-analysis
# Competency-bearing courses × organisation members, status per cell. This is the
# direzione payoff: who is certified / expiring / expired / in progress / missing.
# ============================================================================
def _manageable_orgs(user=None, organization=None):
	"""Org names the caller may oversee (mirrors the Learning Organization scoping):
	System Manager / client-mode Company Admin → all; else the orgs they administer."""
	from lms.worgify import is_client, is_company_admin_of

	user = user or frappe.session.user
	if organization:
		return [organization] if is_company_admin_of(organization, user) else []
	roles = frappe.get_roles(user)
	if "System Manager" in roles or (is_client() and "Company Admin" in roles):
		return frappe.get_all("Learning Organization", pluck="name")
	names = set(frappe.get_all("Learning Organization", {"admin_user": user}, pluck="name"))
	names |= set(frappe.get_all(
		"Learning Organization Member", {"member": user, "member_role": "Admin"}, pluck="parent"
	))
	return list(names)


def _cell(has_cert, expiry, progress, today, soon):
	"""Shared cell status: certified / expiring (<=60d) / expired / in_progress / not_started."""
	if has_cert:
		if expiry:
			ed = frappe.utils.getdate(expiry)
			if ed < today:
				return "expired"
			if ed <= soon:
				return "expiring"
		return "certified"
	if progress and progress >= 100:
		return "certified"
	if progress and progress > 0:
		return "in_progress"
	return "not_started"


def _external_for_personnel(pers_ids, today, soon):
	"""Render External Training Records for a set of Personnel, status-tagged."""
	external = []
	if not pers_ids or not frappe.db.exists("DocType", "External Training Record"):
		return external
	pname = {}
	if frappe.db.exists("DocType", "Personnel"):
		pname = {pp.name: (pp.full_name or pp.name) for pp in frappe.get_all("Personnel", {"name": ["in", pers_ids]}, ["name", "full_name"])}
	for x in frappe.get_all("External Training Record", {"personnel": ["in", pers_ids]}, ["personnel", "title", "issuing_body", "issue_date", "expiry_date"], order_by="issue_date desc"):
		st = "certified"
		if x.expiry_date:
			ed = frappe.utils.getdate(x.expiry_date)
			st = "expired" if ed < today else ("expiring" if ed <= soon else "certified")
		external.append({
			"personnel": pname.get(x.personnel, x.personnel),
			"title": x.title, "issuing_body": x.issuing_body,
			"issue_date": str(x.issue_date) if x.issue_date else "",
			"expiry_date": str(x.expiry_date) if x.expiry_date else "",
			"status": st,
		})
	return external


def _external_for_orgs(org_names, today, soon):
	"""External records for the personnel linked to members of these orgs (B2B/hub lens)."""
	if not org_names or not frappe.db.exists("DocType", "External Training Record"):
		return []
	if not frappe.get_meta("Learning Organization Member").has_field("personnel"):
		return []
	pers_ids = list({
		r.personnel for r in frappe.get_all(
			"Learning Organization Member", {"parent": ["in", org_names]}, ["personnel"]
		) if r.personnel
	})
	return _external_for_personnel(pers_ids, today, soon)


def _is_workforce_caller():
	"""On a client bench, direzione / L&D track the INTERNAL workforce (Personnel),
	not customer-derived org members. Hub and explicit-org calls use the org lens."""
	from lms.worgify import is_client
	if not is_client() or not frappe.db.exists("DocType", "Personnel"):
		return False
	roles = frappe.get_roles()
	return "System Manager" in roles or "Company Admin" in roles


def _workforce_overview(courses, base, today, soon):
	"""Personnel-centric competency matrix: the whole internal workforce x competency
	courses, plus their external qualifications. Personnel without an LMS user show
	'not started' for online courses but still carry their external records."""
	people = frappe.get_all("Personnel", fields=["name", "full_name", "user"], order_by="full_name asc")
	if not people:
		return base
	pers_ids = [pp.name for pp in people]
	course_ids = [c.name for c in courses]
	cert_map = {}
	if course_ids:
		for c in frappe.get_all("LMS Certificate", {"personnel": ["in", pers_ids], "course": ["in", course_ids]}, ["personnel", "course", "expiry_date"]):
			cert_map[(c.personnel, c.course)] = c.expiry_date
	user_to_pers = {pp.user: pp.name for pp in people if pp.user}
	enr_map = {}
	if course_ids and user_to_pers:
		for e in frappe.get_all("LMS Enrollment", {"member": ["in", list(user_to_pers)], "course": ["in", course_ids]}, ["member", "course", "progress"]):
			if e.member in user_to_pers:
				enr_map[(user_to_pers[e.member], e.course)] = e.progress or 0
	summary = {"certified": 0, "expiring": 0, "expired": 0, "in_progress": 0, "not_started": 0}
	rows = []
	for pp in people:
		cells = {}
		for c in course_ids:
			has_cert = (pp.name, c) in cert_map
			s = _cell(has_cert, cert_map.get((pp.name, c)), enr_map.get((pp.name, c), 0), today, soon)
			cells[c] = s
			summary[s] += 1
		rows.append({"member": pp.name, "full_name": pp.full_name or pp.name, "cells": cells})
	base["rows"] = rows
	base["summary"] = summary
	base["external"] = _external_for_personnel(pers_ids, today, soon)
	return base


@frappe.whitelist()
def get_competency_overview(organization=None):
	"""Competency matrix with a per-cell status. On a client bench the default lens is
	the internal WORKFORCE (Personnel); the hub and explicit-organization calls use the
	org-member lens. Also returns external qualifications for the population in view."""
	courses = []
	if frappe.db.exists("DocType", "LMS Course") and frappe.get_meta("LMS Course").has_field(GRANTS_FIELD):
		courses = frappe.get_all("LMS Course", filters={GRANTS_FIELD: 1}, fields=["name", "title"], order_by="title asc")
	base = {"courses": courses, "rows": [], "summary": {}, "external": []}
	today = frappe.utils.getdate()
	soon = frappe.utils.add_days(today, 60)
	# Client direzione / L&D: internal workforce lens.
	if not organization and _is_workforce_caller():
		return _workforce_overview(courses, base, today, soon)
	# Organization lens (hub tenants, B2B client-facing delivery, or a specific org).
	if not frappe.db.exists("DocType", "Learning Organization"):
		return base
	org_names = _manageable_orgs(organization=organization)
	if not org_names:
		return base
	base["external"] = _external_for_orgs(org_names, today, soon)
	if not courses:
		return base
	members = {}
	for r in frappe.get_all("Learning Organization Member", filters={"parent": ["in", org_names]}, fields=["member", "full_name"]):
		members.setdefault(r.member, r.full_name or r.member)
	if not members:
		return base
	member_ids, course_ids = list(members), [c.name for c in courses]
	cert_map = {}
	for c in frappe.get_all("LMS Certificate", filters={"member": ["in", member_ids], "course": ["in", course_ids]}, fields=["member", "course", "expiry_date"]):
		cert_map[(c.member, c.course)] = c.expiry_date
	enr_map = {}
	for e in frappe.get_all("LMS Enrollment", filters={"member": ["in", member_ids], "course": ["in", course_ids]}, fields=["member", "course", "progress"]):
		enr_map[(e.member, e.course)] = e.progress or 0
	summary = {"certified": 0, "expiring": 0, "expired": 0, "in_progress": 0, "not_started": 0}
	rows = []
	for m in sorted(members, key=lambda x: (members[x] or '').lower()):
		cells = {}
		for c in course_ids:
			has_cert = (m, c) in cert_map
			s = _cell(has_cert, cert_map.get((m, c)), enr_map.get((m, c), 0), today, soon)
			cells[c] = s
			summary[s] += 1
		rows.append({"member": m, "full_name": members[m], "cells": cells})
	base["rows"] = rows
	base["summary"] = summary
	return base

@frappe.whitelist()
def record_external_training(personnel, title, issuing_body=None, issue_date=None,
		expiry_date=None, regulatory_reference=None, competency_tags=None, evidence=None):
	"""Record an external training / qualification for a person. Admin-gated.
	The competency then surfaces in Person-360, the MRB register and this overview."""
	roles = frappe.get_roles()
	if "System Manager" not in roles and "Company Admin" not in roles:
		frappe.throw("You are not permitted to record external training.", frappe.PermissionError)
	if not personnel or not title or not issue_date:
		frappe.throw("Personnel, title and issue date are required.")
	doc = frappe.get_doc({
		"doctype": "External Training Record",
		"personnel": personnel, "title": title, "issuing_body": issuing_body,
		"issue_date": issue_date, "expiry_date": expiry_date,
		"regulatory_reference": regulatory_reference, "competency_tags": competency_tags,
		"evidence": evidence,
	})
	if frappe.db.exists("DocType", "Personnel"):
		u = frappe.db.get_value("Personnel", personnel, "user")
		if u:
			doc.member = u
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name}
