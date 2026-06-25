# Copyright (c) 2026, NPM2 Solutions Srl and contributors
# License: AGPLv3 (federates with the Worgify Academy hub — Design 11 §6)
"""Course distribution — vendor (hub) courses land on this client bench as NORMAL
LOCAL courses, fully consumed in-app.

Model: the hub is where WE author vendor courses. A client bench SYNCS the courses it
is entitled to: the content is imported locally (an LMS course package) and tagged with
`worgify_hub_origin`. From then on it is an ordinary local `LMS Course` — it shows in
/lms/courses, the learner enrols and takes it in the local player, and completion mints
a local `LMS Certificate` → competency (the G5 path). Nothing leaves the application;
there is no remote-enrol, no SSO redirect, no separate catalogue page.

The sync is a background concern (scheduled daily + callable). On a single loopback
bench the course already exists locally, so sync simply ADOPTS + tags it; across real
benches it fetches the package from the hub and imports it. All hub I/O is fail-soft.
"""

import base64
import hashlib
import hmac
import json
import time

import frappe
from frappe import _

HUB_ORIGIN_FIELD = "worgify_hub_origin"
HUB_ACQUIRED_FIELD = "worgify_hub_acquired"
HUB_URL_FIELD = "worgify_hub_url"


# --- signed token (compact HMAC-SHA256; byte-compatible with academy.api) ------


def _b64u(b: bytes) -> str:
	return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _sign(payload_b64: str, secret: str) -> str:
	return _b64u(hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest())


def _source():
	return frappe.get_cached_doc("Distribution Source")


def _public_base():
	"""Browser-facing hub base URL (what a learner's browser can reach — e.g. through a
	tunnel / public domain). Falls back to the internal hub_base_url when unset (prod,
	where server-to-server and browser use the same address)."""
	src = _source()
	return (getattr(src, "hub_public_url", None) or src.hub_base_url or "").rstrip("/")


def _secret() -> str:
	from frappe.utils.password import get_decrypted_password

	return get_decrypted_password("Distribution Source", "Distribution Source", "shared_secret")


def mint_token(course=None, learner_email=None, personnel=None, ttl=300, now=None) -> str:
	"""Mint a token byte-compatible with academy.api.verify_enrol_token. `learner_email`
	is set for the SSO launch (so the hub logs that learner in); omitted for plain
	distribution calls (catalogue / request)."""
	src = _source()
	now = int(now if now is not None else time.time())
	payload = {"c": src.distribution_client, "course": course, "e": learner_email,
	           "p": personnel, "iat": now, "exp": now + int(ttl)}
	pb = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
	return pb + "." + _sign(pb, _secret())


# --- configuration / availability --------------------------------------------


def _enabled() -> bool:
	"""Distribution runs only on a configured client bench with the feature on."""
	if not frappe.db.exists("DocType", "Distribution Source"):
		return False
	try:
		from lms.worgify import is_client, feature_enabled
		if not is_client() or not feature_enabled("enable_distribution"):
			return False
	except Exception:
		pass
	src = frappe.get_cached_doc("Distribution Source")
	return bool(src.enabled and src.hub_base_url and src.distribution_client)


def _hub_get(method, params):
	from frappe.integrations.utils import make_get_request

	src = _source()
	url = f"{src.hub_base_url.rstrip('/')}/api/method/{method}"
	resp = make_get_request(url, params=params)
	return (resp or {}).get("message", resp) or {}


# --- the "da hub" marker on LMS Course ----------------------------------------


def ensure_hub_origin_field():
	"""Hidden markers on LMS Course: `worgify_hub_origin` = the hub course id a local
	course was distributed from (also drives the 'from hub' badge); `worgify_hub_acquired`
	= whether the company has acquired (licensed) it. Created on every fork bench."""
	if not frappe.db.exists("DocType", "LMS Course"):
		return
	if not frappe.db.exists("Custom Field", f"LMS Course-{HUB_ORIGIN_FIELD}"):
		frappe.get_doc({
			"doctype": "Custom Field", "dt": "LMS Course", "fieldname": HUB_ORIGIN_FIELD,
			"label": "Worgify Hub Origin", "fieldtype": "Data", "read_only": 1,
			"no_copy": 1, "hidden": 1, "insert_after": "tags",
		}).insert(ignore_permissions=True)
	if not frappe.db.exists("Custom Field", f"LMS Course-{HUB_ACQUIRED_FIELD}"):
		frappe.get_doc({
			"doctype": "Custom Field", "dt": "LMS Course", "fieldname": HUB_ACQUIRED_FIELD,
			"label": "Worgify Hub Acquired", "fieldtype": "Check", "default": "0",
			"read_only": 1, "no_copy": 1, "hidden": 1, "insert_after": HUB_ORIGIN_FIELD,
		}).insert(ignore_permissions=True)
	if not frappe.db.exists("Custom Field", f"LMS Course-{HUB_URL_FIELD}"):
		frappe.get_doc({
			"doctype": "Custom Field", "dt": "LMS Course", "fieldname": HUB_URL_FIELD,
			"label": "Worgify Hub Player URL", "fieldtype": "Data", "read_only": 1,
			"no_copy": 1, "hidden": 1, "insert_after": HUB_ACQUIRED_FIELD,
		}).insert(ignore_permissions=True)


# --- distribution: hub courses -> local courses -------------------------------


def available_hub_courses():
	"""Entitled vendor courses on the hub (metadata), fail-soft to []."""
	if not _enabled():
		return []
	try:
		data = _hub_get("academy.api.catalog", {
			"distribution_client": _source().distribution_client,
			"token": mint_token(ttl=120),
		})
		return data.get("courses", [])
	except Exception:
		frappe.log_error(title="worgify: hub catalog fetch failed", message=frappe.get_traceback())
		return []


def _create_shell(cid, meta):
	"""A metadata-only local LMS Course (NO chapters/lessons) — the content is served
	LIVE from the hub and embedded in-app, never copied here. Returns the local name."""
	doc = frappe.get_doc({
		"doctype": "LMS Course",
		"title": meta.get("title") or cid,
		"short_introduction": (meta.get("intro") or "Worgify Academy course")[:140],
		"description": meta.get("intro") or "Served live from the Worgify Academy hub.",
		"image": meta.get("image"),
		"published": 0,
	})
	doc.append("instructors", {"instructor": frappe.session.user})
	doc.flags.ignore_worgify_lock = True
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def sync_hub_courses():
	"""Make GRANTED vendor courses available on this bench as local SHELLS — metadata
	only, NO content copied: the content is served LIVE from the hub, embedded in-app
	(`worgify_hub_url`). Free courses, plus paid courses granted after an offline deal.
	Ungranted paid courses stay requestable. Idempotent. Admin-gated; daily + callable."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only an administrator can sync hub courses."), frappe.PermissionError)
	if not _enabled():
		return {"activated": [], "note": "distribution not configured / disabled"}
	base = _public_base()  # browser-facing URL for the embedded player
	activated = []
	for hc in available_hub_courses():
		cid = hc.get("course")
		if not cid or not hc.get("granted"):
			continue  # ungranted paid course -> requestable only
		if frappe.db.exists("LMS Course", {HUB_ORIGIN_FIELD: cid}):
			continue  # already shelled
		if frappe.db.exists("LMS Course", cid):
			local = cid  # adopt an already-present course (loopback); its content is ignored
		else:
			local = _create_shell(cid, hc)  # production: empty metadata-only shell
		frappe.db.set_value("LMS Course", local, {
			HUB_ORIGIN_FIELD: cid,
			HUB_URL_FIELD: f"{base}/lms/courses/{cid}",
			"published": 1,
			# Hub courses are competency-bearing → a completion (pulled back) mints a
			# local certificate. (db.set_value bypasses the read-only guard.)
			"grants_training_certificate": 1,
		})
		activated.append(local)
	frappe.db.commit()
	return {"activated": activated}


@frappe.whitelist()
def list_requestable():
	"""PAID hub courses visible to this bench but NOT yet granted — i.e. requestable
	(admin view). Free / already-granted courses are normal local courses, not here."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	out = []
	for hc in available_hub_courses():
		if hc.get("granted"):
			continue
		if frappe.db.exists("LMS Course", {HUB_ORIGIN_FIELD: hc.get("course")}):
			continue  # already present locally
		out.append({
			"course": hc.get("course"), "title": hc.get("title") or hc.get("course"),
			"intro": hc.get("intro"), "price": hc.get("price"), "currency": hc.get("currency"),
		})
	return out


@frappe.whitelist()
def request_hub_course(course):
	"""Send a request (contact only) to the vendor for a PAID hub course. No purchase
	happens in-app: we handle it offline and then grant access, after which the next sync
	activates it. `course` = the HUB course id. Admin-only."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only an administrator can request courses."), frappe.PermissionError)
	if not _enabled():
		frappe.throw(_("Course distribution is not configured on this bench."))
	try:
		resp = _hub_get("academy.api.request_access", {
			"distribution_client": _source().distribution_client,
			"token": mint_token(course=course, ttl=120),
			"course": course,
		})
	except Exception:
		frappe.log_error(title=f"worgify: request for {course} failed", message=frappe.get_traceback())
		frappe.throw(_("Could not send the request to the hub. Try again."))
	return resp or {"ok": True}


@frappe.whitelist()
def get_hub_launch_url(course):
	"""For a local hub-shell course, mint a per-learner token and return the hub SSO
	launch URL to embed. The hub logs the current learner in and serves the live player.
	Returns None when the course is not a hub course / distribution is off."""
	origin = frappe.db.get_value("LMS Course", course, HUB_ORIGIN_FIELD)
	if not origin or not _enabled():
		return None
	token = mint_token(course=origin, learner_email=frappe.session.user, ttl=600)
	base = _public_base()
	return f"{base}/api/method/academy.api.sso_launch?token={token}&course={origin}"


@frappe.whitelist()
def pull_hub_completions():
	"""Pull completed hub-course enrolments back from the hub and turn each into local
	competency evidence: mark the local shell enrolment complete + mint a local
	LMS Certificate (→ Person-360 + MRB + Competency Overview). Idempotent; fail-soft.
	Scheduled daily + callable."""
	if not _enabled():
		return {"minted": 0, "note": "distribution off"}
	src = _source()
	try:
		data = _hub_get("academy.api.completions_since", {
			"distribution_client": src.distribution_client,
			"token": mint_token(ttl=120),
			"cursor": src.last_cursor or "",
		})
	except Exception:
		frappe.log_error(title="worgify: completions pull failed", message=frappe.get_traceback())
		return {"minted": 0}
	from lms.worgify_competency import issue_completion_certificate

	minted = 0
	for row in data.get("completions", []):
		email, hub_course = row.get("member"), row.get("course")
		if not email or not hub_course:
			continue
		shell = frappe.db.get_value("LMS Course", {HUB_ORIGIN_FIELD: hub_course}, "name")
		if not shell or not frappe.db.exists("User", email):
			continue
		if not frappe.db.exists("LMS Enrollment", {"member": email, "course": shell}):
			frappe.get_doc({"doctype": "LMS Enrollment", "member": email, "course": shell}).insert(
				ignore_permissions=True
			)
		frappe.db.set_value("LMS Enrollment", {"member": email, "course": shell}, "progress", 100)
		if issue_completion_certificate(shell, email):
			minted += 1
	if data.get("cursor"):
		frappe.db.set_value("Distribution Source", "Distribution Source", "last_cursor", data["cursor"])
	frappe.db.commit()
	return {"minted": minted, "cursor": data.get("cursor")}


def guard_hub_course_edit(doc, method=None):
	"""A vendor (hub) course is read-only on a client bench — only attendable, never
	edited. Blocks form/API saves of a course tagged `worgify_hub_origin`. System writes
	(course statistics etc. via `db.set_value`) bypass `validate`, so they are unaffected;
	content imports insert the course BEFORE the marker is set, so they pass too."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import:
		return
	if getattr(doc, HUB_ORIGIN_FIELD, None) and not doc.flags.get("ignore_worgify_lock"):
		frappe.throw(_("This course is provided by the Worgify Academy hub and cannot be edited here."))
