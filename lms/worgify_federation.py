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
HUB_LESSON_FIELD = "worgify_hub_lesson"  # on Course Lesson: the hub lesson a stub mirrors
HUB_QUIZ_FIELD = "worgify_hub_quiz"  # on LMS Quiz: the hub quiz a stub mirrors


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
	# headless: mark each local lesson STUB with the hub lesson it mirrors (content is
	# fetched live from the hub at view time, never stored locally)
	if frappe.db.exists("DocType", "Course Lesson") and not frappe.db.exists(
		"Custom Field", f"Course Lesson-{HUB_LESSON_FIELD}"
	):
		frappe.get_doc({
			"doctype": "Custom Field", "dt": "Course Lesson", "fieldname": HUB_LESSON_FIELD,
			"label": "Worgify Hub Lesson", "fieldtype": "Data", "read_only": 1,
			"no_copy": 1, "hidden": 1,
		}).insert(ignore_permissions=True)
	# headless: mark each local quiz STUB with the hub quiz it mirrors (questions fetched
	# live, grading done on the hub)
	if frappe.db.exists("DocType", "LMS Quiz") and not frappe.db.exists(
		"Custom Field", f"LMS Quiz-{HUB_QUIZ_FIELD}"
	):
		frappe.get_doc({
			"doctype": "Custom Field", "dt": "LMS Quiz", "fieldname": HUB_QUIZ_FIELD,
			"label": "Worgify Hub Quiz", "fieldtype": "Data", "read_only": 1,
			"no_copy": 1, "hidden": 1,
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


def _build_structure(local_course, hub_course):
	"""Mirror the hub course's STRUCTURE (chapters + lessons) as local stubs — titles +
	order only, empty body. Each lesson stub carries `worgify_hub_lesson` so its content
	can be fetched LIVE at view time. Idempotent. Returns the number of lesson stubs made.
	(Chapter/Lesson References are inserted directly so we never save the locked LMS Course.)"""
	if not _enabled() or frappe.db.exists("Chapter Reference", {"parent": local_course}):
		return 0
	data = _hub_get("academy.api.course_outline", {
		"distribution_client": _source().distribution_client,
		"token": mint_token(course=hub_course, ttl=120),
		"course": hub_course,
	})
	made = 0
	for ci, ch in enumerate(data.get("chapters", []), start=1):
		chap = frappe.get_doc({
			"doctype": "Course Chapter", "course": local_course, "title": ch.get("title") or "Module",
		}).insert(ignore_permissions=True)
		for li, ls in enumerate(ch.get("lessons", []), start=1):
			lesson = frappe.get_doc({
				"doctype": "Course Lesson", "chapter": chap.name, "course": local_course,
				"title": ls.get("title") or "Lesson", "body": "", "content": "",
				HUB_LESSON_FIELD: ls.get("lesson"),
			})
			lesson.flags.ignore_worgify_lock = True
			lesson.insert(ignore_permissions=True)
			# quiz stub: questions are fetched live + graded on the hub (see get_quiz_*_proxied)
			q = ls.get("quiz")
			if q and q.get("quiz") and not frappe.db.exists("LMS Quiz", {HUB_QUIZ_FIELD: q["quiz"]}):
				stub = frappe.get_doc({
					"doctype": "LMS Quiz", "title": q.get("title") or "Quiz",
					"course": local_course, "lesson": lesson.name,
					HUB_QUIZ_FIELD: q["quiz"],
				})
				stub.insert(ignore_permissions=True)
				# the stub has no local questions, so validate() zeroes total_marks; force the
				# hub's basis so the local submission's score/percentage math is correct
				frappe.db.set_value("LMS Quiz", stub.name, {
					"total_marks": q.get("total_marks") or 0,
					"passing_percentage": q.get("passing_percentage") or 0,
				})
			frappe.get_doc({
				"doctype": "Lesson Reference", "parent": chap.name, "parenttype": "Course Chapter",
				"parentfield": "lessons", "idx": li, "lesson": lesson.name,
			}).insert(ignore_permissions=True)
			made += 1
		frappe.get_doc({
			"doctype": "Chapter Reference", "parent": local_course, "parenttype": "LMS Course",
			"parentfield": "chapters", "idx": ci, "chapter": chap.name,
		}).insert(ignore_permissions=True)
	return made


@frappe.whitelist()
def sync_hub_courses():
	"""Headless distribution: for each GRANTED vendor course, ensure a local course (a
	metadata shell) + mirror its STRUCTURE as local chapter/lesson stubs (no content).
	Lesson content is fetched LIVE at view time (`get_lesson_proxied`); nothing is copied.
	Free courses + paid courses granted after a deal. Idempotent. Admin-gated; daily."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only an administrator can sync hub courses."), frappe.PermissionError)
	if not _enabled():
		return {"activated": [], "note": "distribution not configured / disabled"}
	activated = []
	for hc in available_hub_courses():
		cid = hc.get("course")
		if not cid or not hc.get("granted"):
			continue  # ungranted paid course -> requestable only
		local = frappe.db.get_value("LMS Course", {HUB_ORIGIN_FIELD: cid}, "name")
		if not local:
			local = cid if frappe.db.exists("LMS Course", cid) else _create_shell(cid, hc)
			frappe.db.set_value("LMS Course", local, {
				HUB_ORIGIN_FIELD: cid, "published": 1,
				# competency-bearing → local completion mints a certificate
				"grants_training_certificate": 1,
			})
		built = _build_structure(local, cid)  # idempotent (no-op if already built)
		activated.append({"course": local, "lessons_built": built})
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


def _remap_content_quizzes(content):
	"""Rewrite hub quiz ids embedded in EditorJS quiz blocks → the local quiz stub, so the
	in-content quiz player (a same-origin /lms/quiz/<id> iframe) hits our proxied stub."""
	try:
		doc = json.loads(content) if isinstance(content, str) else content
	except Exception:
		return content
	changed = False
	for block in (doc.get("blocks") or []) if isinstance(doc, dict) else []:
		if block.get("type") == "quiz":
			hub_q = (block.get("data") or {}).get("quiz")
			local = hub_q and frappe.db.get_value("LMS Quiz", {HUB_QUIZ_FIELD: hub_q}, "name")
			if local and local != hub_q:
				block["data"]["quiz"] = local
				changed = True
	return json.dumps(doc) if changed else content


@frappe.whitelist(allow_guest=True)
def get_lesson_proxied(course, chapter, lesson):
	"""Override of `lms.lms.utils.get_lesson` (wired via override_whitelisted_methods).
	Renders the lesson normally, but for a HUB course injects the content fetched LIVE
	from the hub — the local stub has an empty body, so nothing is stored on this bench.
	Falls back to the (empty) local lesson if the hub is unreachable."""
	from lms.lms.utils import get_lesson as _orig_get_lesson

	data = _orig_get_lesson(course, chapter, lesson)
	if not isinstance(data, dict) or not data:
		return data
	origin = frappe.db.get_value("LMS Course", course, HUB_ORIGIN_FIELD)
	hub_lesson = data.get("name") and frappe.db.get_value("Course Lesson", data["name"], HUB_LESSON_FIELD)
	if not origin or not hub_lesson or not _enabled():
		return data
	try:
		content = _hub_get("academy.api.lesson_content", {
			"distribution_client": _source().distribution_client,
			"token": mint_token(course=origin, ttl=120),
			"course": origin, "lesson": hub_lesson,
		})
		for k in ("content", "body", "youtube", "quiz_id", "question", "file_type", "instructor_notes"):
			if content.get(k) is not None:
				data[k] = content.get(k)
		# the hub's quiz_id is meaningless locally → point at our local quiz stub
		if data.get("quiz_id"):
			data["quiz_id"] = frappe.db.get_value(
				"LMS Quiz", {HUB_QUIZ_FIELD: data["quiz_id"]}, "name"
			) or None
		# remap quiz blocks embedded in the EditorJS content (hub quiz id → local stub)
		if data.get("content"):
			data["content"] = _remap_content_quizzes(data["content"])
	except Exception:
		frappe.log_error(title=f"worgify: live lesson fetch failed ({hub_lesson})",
		                 message=frappe.get_traceback())
	return data


@frappe.whitelist(allow_guest=True)
def get_quiz_with_questions_proxied(quiz):
	"""Override of `lms.lms.utils.get_quiz_with_questions`: for a hub quiz stub, fetch the
	questions/options LIVE from the hub (answers stripped there); else render the local quiz."""
	from lms.lms.utils import get_quiz_with_questions as _orig

	hub_quiz = frappe.db.get_value("LMS Quiz", quiz, HUB_QUIZ_FIELD) if frappe.db.exists("LMS Quiz", quiz) else None
	if not hub_quiz or not _enabled():
		return _orig(quiz)
	origin = frappe.db.get_value("LMS Quiz", quiz, "course")
	origin = frappe.db.get_value("LMS Course", origin, HUB_ORIGIN_FIELD) or origin
	data = _hub_get("academy.api.quiz_data", {
		"distribution_client": _source().distribution_client,
		"token": mint_token(course=origin, ttl=120),
		"course": origin, "quiz": hub_quiz,
	})
	# present the quiz under its LOCAL stub name (the frontend submits with this id)
	if data.get("quiz"):
		data["quiz"]["name"] = quiz
	return data


@frappe.whitelist(allow_guest=True)
def submit_quiz_proxied(quiz, results=None):
	"""Override of `lms.lms.doctype.lms_quiz.lms_quiz.submit_quiz`: for a hub quiz, grade
	ON THE HUB (it owns the answers) then record a LOCAL submission + progress; else local."""
	from lms.lms.doctype.lms_quiz.lms_quiz import submit_quiz as _orig

	hub_quiz = frappe.db.get_value("LMS Quiz", quiz, HUB_QUIZ_FIELD) if frappe.db.exists("LMS Quiz", quiz) else None
	if not hub_quiz or not _enabled():
		return _orig(quiz, results)

	from lms.lms.doctype.lms_quiz.lms_quiz import create_submission, save_progress_after_quiz

	stub = frappe.db.get_value(
		"LMS Quiz", quiz, ["name", "course", "lesson", "total_marks", "passing_percentage"], as_dict=1
	)
	origin = frappe.db.get_value("LMS Course", stub.course, HUB_ORIGIN_FIELD) or stub.course
	graded = _hub_get("academy.api.grade_quiz", {
		"distribution_client": _source().distribution_client,
		"token": mint_token(course=origin, ttl=120),
		"course": origin, "quiz": hub_quiz,
		# results arrives already JSON-encoded from the frontend — don't double-encode it
		"results": results if isinstance(results, str) else json.dumps(results or []),
	})
	rows = graded.get("results", [])
	for r in rows:
		r.pop("question_name", None)  # hub question id → no local Link; keep question text/answer/marks
	total = graded.get("total_marks") or stub.total_marks or 0
	passing = graded.get("passing_percentage") or stub.passing_percentage or 0
	submission = create_submission(quiz, rows, total, passing)
	percentage = submission.percentage or 0
	# gate progress on the HUB's passing %, with the local lesson/course of the stub
	save_progress_after_quiz(
		frappe._dict(lesson=stub.lesson, course=stub.course, passing_percentage=passing), percentage
	)
	return {
		"score": submission.score, "score_out_of": submission.score_out_of,
		"submission": submission.name, "pass": percentage >= passing,
		"percentage": percentage, "is_open_ended": graded.get("is_open_ended", False),
	}


@frappe.whitelist(allow_guest=True)
def check_answer_proxied(quiz, question, question_type, answers):
	"""Override of `lms.lms.doctype.lms_quiz.lms_quiz.check_answer`: instant feedback for a
	hub quiz is graded ON THE HUB; else local."""
	from lms.lms.doctype.lms_quiz.lms_quiz import check_answer as _orig

	hub_quiz = frappe.db.get_value("LMS Quiz", quiz, HUB_QUIZ_FIELD) if frappe.db.exists("LMS Quiz", quiz) else None
	if not hub_quiz or not _enabled():
		return _orig(quiz, question, question_type, answers)
	origin = frappe.db.get_value("LMS Quiz", quiz, "course")
	origin = frappe.db.get_value("LMS Course", origin, HUB_ORIGIN_FIELD) or origin
	return _hub_get("academy.api.check_answer", {
		"distribution_client": _source().distribution_client,
		"token": mint_token(course=origin, ttl=120),
		"course": origin, "quiz": hub_quiz, "question": question,
		"question_type": question_type, "answers": answers,
	})


def guard_hub_course_edit(doc, method=None):
	"""A vendor (hub) course is read-only on a client bench — only attendable, never
	edited. Blocks form/API saves of a course tagged `worgify_hub_origin`. System writes
	(course statistics etc. via `db.set_value`) bypass `validate`, so they are unaffected;
	content imports insert the course BEFORE the marker is set, so they pass too."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import:
		return
	if getattr(doc, HUB_ORIGIN_FIELD, None) and not doc.flags.get("ignore_worgify_lock"):
		frappe.throw(_("This course is provided by the Worgify Academy hub and cannot be edited here."))
