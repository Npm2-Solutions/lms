import frappe

from . import __version__ as app_version

app_name = "frappe_lms"
app_title = "Learning"
app_publisher = "Frappe"
app_description = "Open Source Learning Management System built with Frappe Framework"
app_icon_url = "/assets/lms/images/lms-logo.png"
app_icon_title = "Learning"
app_icon_route = "/lms"
app_color = "grey"
app_email = "jannat@frappe.io"
app_license = "AGPL"
required_apps = ["frappe/payments"]


def get_lms_path():
	path = "lms"
	if frappe.conf and frappe.conf.get("lms_path"):
		path = frappe.conf.get("lms_path")
	return path.strip("/")


# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/lms/css/lms.css"
# app_include_js = "/assets/lms/js/lms.js"

# include js, css files in header of web template
web_include_css = "lms.bundle.css"
# web_include_css = "/assets/lms/css/lms.css"
web_include_js = []

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "lms/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "lms.install.before_install"
after_install = "lms.install.after_install"
after_sync = "lms.install.after_sync"
before_uninstall = "lms.install.before_uninstall"
setup_wizard_complete = "lms.demo.demo_data.create_demo_data"
after_migrate = [
	"lms.sqlite.build_index_in_background",
	# Worgify Academy: ensure the role set (Company Admin, …).
	"lms.worgify.ensure_worgify_roles",
	# Worgify Academy competency bridge — adds the guarded `personnel` link to LMS
	# Certificate (client benches with optisuites only; no-op on the hub).
	"lms.worgify_competency.ensure_competency_fields",
	# Worgify Academy group layer — mirror optisuites Customers as Learning
	# Organizations + seed members from portal users (client only; no-op on the hub).
	"lms.worgify_groups.sync_organizations_from_customers",
	# Worgify Academy — ensure the "from hub" marker on LMS Course (distribution).
	"lms.worgify_federation.ensure_hub_origin_field",
]

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "lms.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"LMS Certificate": "lms.lms.doctype.lms_certificate.lms_certificate.get_permission_query_conditions",
	# A Company Admin sees only the organization(s) they run.
	"Learning Organization": "lms.worgify_groups.get_permission_query_conditions",
}

has_permission = {
	"LMS Live Class": "lms.lms.doctype.lms_live_class.lms_live_class.has_permission",
	"LMS Batch": "lms.lms.doctype.lms_batch.lms_batch.has_permission",
	"LMS Program": "lms.lms.doctype.lms_program.lms_program.has_permission",
	"LMS Certificate": "lms.lms.doctype.lms_certificate.lms_certificate.has_permission",
	"Course Lesson": "lms.lms.doctype.course_lesson.course_lesson.has_permission",
	"File": "lms.lms.permissions.file_has_permission",
	"Learning Organization": "lms.worgify_groups.has_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Web Template": "lms.overrides.web_template.CustomWebTemplate",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"*": {
		"on_change": [
			"lms.lms.doctype.lms_badge.lms_badge.process_badges",
		]
	},
	"Discussion Reply": {
		"after_insert": "lms.lms.utils.handle_notifications",
		"validate": "lms.lms.utils.validate_discussion_reply",
	},
	"Notification Log": {"on_change": "lms.lms.utils.publish_notifications"},
	"User": {
		"validate": "lms.lms.user.validate_username_duplicates",
		"before_insert": "lms.lms.user.add_lms_student_role",
	},
	# Worgify Academy: stamp the competency owner (Personnel) on issued certificates.
	"LMS Certificate": {
		"after_insert": "lms.worgify_competency.on_lms_certificate",
	},
	# Worgify: auto-issue the competency certificate on self-paced completion.
	"LMS Course Progress": {
		"on_update": "lms.worgify_competency.on_course_progress",
	},
	# Worgify: vendor (hub) courses are read-only on a client bench.
	"LMS Course": {
		"validate": "lms.worgify_federation.guard_hub_course_edit",
	},
}

# Worgify Academy — cross-app integration (Design 11)
# ---------------------------------------------------
# Consumed by optisuites (Person-360) and recordbook (MRB dossier) WHEN PRESENT;
# absent consumers simply ignore these, so the fork stays standalone (hub) too.

# Surface issued training certificates into the optisuites Personnel 360 view.
personnel_role_profiles = [
	{
		"doctype": "LMS Certificate",
		"personnel_field": "personnel",
		"label": "Training Certificate",
		"icon": "education",
		"fields": ["course_title", "issue_date", "expiry_date"],
	},
	{
		"doctype": "External Training Record",
		"personnel_field": "personnel",
		"label": "External Training",
		"icon": "education",
		"fields": ["title", "issuing_body", "issue_date", "expiry_date"],
	},
]

# Contribute the org-wide Personnel Training & Competency register to the MRB.
record_book_contributors = {
	"training": {
		"label": "Training & Competency",
		"icon": "education",
		"app_version_contract": "1.0",
		"sections": {
			"training_register": {
				"title": "Personnel Training & Competency",
				"description": "Organisation-wide register of personnel training certificates (LMS-derived), with validity status.",
				"builder": "lms.worgify_competency.build_training_register",
				"supported_scopes": ["Project", "Assembly", "JointList", "Organization"],
				"render_orientation": "Landscape",
				"pf_context_keys": ["doc", "scope"],
			},
		},
	},
}

# Scheduled Tasks
# ---------------
scheduler_events = {
	"all": [
		"lms.sqlite.build_index_in_background",
	],
	"hourly": [
		"lms.lms.doctype.lms_certificate_request.lms_certificate_request.schedule_evals",
		"lms.lms.doctype.lms_course.lms_course.update_course_statistics",
		"lms.lms.doctype.lms_certificate_request.lms_certificate_request.mark_eval_as_completed",
		"lms.lms.doctype.lms_live_class.lms_live_class.update_attendance",
	],
	"daily": [
		"lms.job.doctype.job_opportunity.job_opportunity.update_job_openings",
		"lms.lms.doctype.lms_payment.lms_payment.send_payment_reminder",
		"lms.lms.doctype.lms_batch.lms_batch.send_batch_start_reminder",
		"lms.lms.doctype.lms_live_class.lms_live_class.send_live_class_reminder",
		"lms.lms.doctype.lms_course.lms_course.send_notification_for_published_courses",
		# Worgify: reconcile competency certificates for completed courses (safety net).
		"lms.worgify_competency.reconcile_completions",
		# Worgify: distribute entitled vendor courses from the hub (structure stubs;
		# content served live). Completion is local → competency via the G5 path.
		"lms.worgify_federation.sync_hub_courses",
	],
}

fixtures = ["Custom Field", "Function", "Industry", "LMS Category"]

# Testing
# -------

# before_tests = "lms.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	# Worgify: headless content — inject hub lesson content / quiz live for hub courses.
	"lms.lms.utils.get_lesson": "lms.worgify_federation.get_lesson_proxied",
	"lms.lms.utils.get_quiz_with_questions": "lms.worgify_federation.get_quiz_with_questions_proxied",
	"lms.lms.doctype.lms_quiz.lms_quiz.submit_quiz": "lms.worgify_federation.submit_quiz_proxied",
	"lms.lms.doctype.lms_quiz.lms_quiz.check_answer": "lms.worgify_federation.check_answer_proxied",
	# "frappe.desk.search.get_names_for_mentions": "lms.lms.utils.get_names_for_mentions",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "lms.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Add all simple route rules here
website_route_rules = [
	{"from_route": f"/{get_lms_path()}/<path:app_path>", "to_route": "_lms"},
	{"from_route": f"/{get_lms_path()}", "to_route": "_lms"},
	{
		"from_route": "/courses/<course_name>/<certificate_id>",
		"to_route": "certificate",
	},
]

website_redirects = [
	{"source": "/update-profile", "target": "/edit-profile"},
	{"source": "/courses", "target": f"/{get_lms_path()}/courses"},
	{
		"source": r"^/courses/.*$",
		"target": f"/{get_lms_path()}/courses",
	},
	{"source": "/batches", "target": f"/{get_lms_path()}/batches"},
	{
		"source": r"/batches/(.*)",
		"target": f"/{get_lms_path()}/batches",
		"match_with_query_string": True,
	},
	{"source": "/job-openings", "target": f"/{get_lms_path()}/job-openings"},
	{
		"source": r"/job-openings/(.*)",
		"target": f"/{get_lms_path()}/job-openings",
		"match_with_query_string": True,
	},
	{"source": "/statistics", "target": f"/{get_lms_path()}/statistics"},
	{"source": "_lms", "target": f"/{get_lms_path()}"},
]

update_website_context = [
	"lms.widgets.update_website_context",
]

jinja = {
	"methods": [
		"lms.lms.utils.get_lesson_count",
		"lms.lms.utils.get_instructors",
		"lms.lms.utils.get_lesson_index",
		"lms.lms.utils.get_lesson_url",
		"lms.lms.utils.get_lms_route",
		"lms.lms.utils.is_instructor",
		"lms.lms.utils.get_palette",
	],
	"filters": [],
}

extend_bootinfo = [
	"lms.lms.utils.extend_bootinfo",
]
## Specify the additional tabs to be included in the user profile page.
## Each entry must be a subclass of lms.lms.plugins.ProfileTab
# profile_tabs = []

## Specify the extension to be used to control what scripts and stylesheets
## to be included in lesson pages. The specified value must be be a
## subclass of lms.plugins.PageExtension
# lms_lesson_page_extension = None

# lms_lesson_page_extensions = [
# 	"lms.plugins.LiveCodeExtension"
# ]

has_website_permission = {
	"LMS Certificate Evaluation": "lms.lms.doctype.lms_certificate_evaluation.lms_certificate_evaluation.has_website_permission",
	"LMS Certificate": "lms.lms.doctype.lms_certificate.lms_certificate.has_website_permission",
}

## Markdown Macros for Lessons
lms_markdown_macro_renderers = {
	"Exercise": "lms.plugins.exercise_renderer",
	"Quiz": "lms.plugins.quiz_renderer",
	"YouTubeVideo": "lms.plugins.youtube_video_renderer",
	"Video": "lms.plugins.video_renderer",
	"Assignment": "lms.plugins.assignment_renderer",
	"Embed": "lms.plugins.embed_renderer",
	"Audio": "lms.plugins.audio_renderer",
	"PDF": "lms.plugins.pdf_renderer",
}

page_renderer = [
	"lms.page_renderers.SCORMRenderer",
]

# set this to "/" to have profiles on the top-level
profile_url_prefix = "/users/"

signup_form_template = "lms.plugins.show_custom_signup"

on_login = "lms.lms.user.on_login"

get_site_info = "lms.activation.get_site_info"

# Opti Academy fork: the launcher tile is provided by our `training` app (-> /lms),
# so the engine's own "Learning"/"Frappe Learning" tile is suppressed to keep ONE
# unified entry for the user (no green Frappe tile).
add_to_apps_screen = []

sqlite_search = ["lms.sqlite.LearningSearch"]
auth_hooks = ["lms.auth.authenticate"]
require_type_annotated_api_methods = True
