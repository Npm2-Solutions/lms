"""Babel extractor for Notifications shipped as JSON.

`bench generate-pot-file` does not read Notification templates, so the
`{{ _("…") }}` sentences of a subject or message never reach main.pot and
`bench update-po-files` drops their translations. Wired in
`babel_extractors.csv`; each Jinja field goes through frappe's own template
extractor. (A copy of worgify.gettext.notification: lms does not require
worgify.)
"""

import io
import json

from frappe.gettext.extractors.html_template import extract as extract_template

TEMPLATE_FIELDS = ("subject", "message", "notification_title", "notification_message")


def extract(fileobj, keywords=None, comment_tags=None, options=None):
	"""Yield (lineno, funcname, message, comments) for every `_()` in a Notification's templates."""
	try:
		data = json.load(fileobj)
	except ValueError:
		return

	for doc in data if isinstance(data, list) else [data]:
		if not isinstance(doc, dict) or doc.get("doctype") != "Notification":
			continue
		for field in TEMPLATE_FIELDS:
			template = doc.get(field)
			if not template or not isinstance(template, str):
				continue
			seen = set()
			for _lineno, funcname, messages, comments in extract_template(
				io.BytesIO(template.encode("utf-8")), keywords or (), comment_tags or (), options or {}
			):
				key = (funcname, messages if isinstance(messages, str) else tuple(messages))
				if key in seen:
					continue
				seen.add(key)
				yield None, funcname, messages, [f"Notification: {doc.get('name')} ({field})", *comments]
