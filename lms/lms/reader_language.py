# Copyright (c) 2026, NPM2 Solutions Srl and contributors
# For license information, please see license.txt

"""An e-mail is written in the language of whoever reads it.

A mail built with `_()` speaks the language of whoever runs the request or the
job, not the recipient's. With the worgify kernel installed the readers are
split by language and the mail is written once per language; lms stays
standalone: without worgify it sends once, as before.

	for lang, recipients, cc, bcc in readers(recipients, cc, bcc):
		with in_language(lang):
			subject = _("...")
			frappe.sendmail(recipients=recipients, cc=cc, bcc=bcc, subject=subject, ...)
"""

from contextlib import nullcontext

from frappe.utils import split_emails

try:
	from worgify.utils.language import by_language as _by_language
	from worgify.utils.language import in_language as _in_language
except ImportError:  # lms without the worgify kernel
	_by_language = _in_language = None


def _as_list(people):
	if not people:
		return []
	if isinstance(people, str):
		return split_emails(people)
	return list(people)


def readers(recipients=None, cc=None, bcc=None):
	"""[(lang, recipients, cc, bcc)] — one group per language of the readers.

	Without the kernel (or with nobody to read it) a single group with lang None
	carrying the lists exactly as given."""
	if _by_language is None:
		return [(None, recipients, cc, bcc)]
	groups = _by_language(_as_list(recipients), _as_list(cc), _as_list(bcc))
	if not groups:
		return [(None, recipients, cc, bcc)]
	return [(lang, to, copy, blind) for lang, (to, copy, blind) in groups.items()]


def in_language(lang):
	"""Render in `lang` and stay in it; a no-op without the kernel or a language."""
	if _in_language is None or lang is None:
		return nullcontext()
	return _in_language(lang)
