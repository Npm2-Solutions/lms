# Copyright (c) 2026, NPM2 Solutions Srl and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from lms.worgify_groups import generate_join_code


class LearningOrganization(Document):
	def before_insert(self):
		if not self.join_code:
			self.join_code = generate_join_code()

	def validate(self):
		# one membership row per user
		seen, kept = set(), []
		for m in self.members:
			if m.member and m.member not in seen:
				seen.add(m.member)
				kept.append(m)
		self.members = kept
