# Copyright (c) 2026, NPM2 Solutions Srl and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from lms.worgify import _FEATURE_DEFAULTS


class WorgifySettings(Document):
	def before_save(self):
		"""When the admin flips the platform mode, seed the feature flags to that
		mode's defaults (hub → marketplace/distribution/stripe on; client →
		competency on). The admin can still override individual flags afterwards."""
		old = frappe.db.get_single_value("Worgify Settings", "worgify_mode")
		new = (self.worgify_mode or "").strip().lower()
		if old and (old or "").strip().lower() != new:
			for flag, defaults in _FEATURE_DEFAULTS.items():
				if self.meta.has_field(flag):
					self.set(flag, 1 if defaults.get(new, False) else 0)
