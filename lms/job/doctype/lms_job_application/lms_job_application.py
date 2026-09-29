# Copyright (c) 2024, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from lms.lms.reader_language import in_language, readers


class LMSJobApplication(Document):
	def validate(self):
		self.validate_duplicate()

	def after_insert(self):
		job_owner = frappe.get_value("Job Opportunity", self.job, "owner")
		if job_owner:
			frappe.share.add_docshare("LMS Job Application", self.name, job_owner, read=1)

		outgoing_email_account = frappe.get_cached_value(
			"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "name"
		)
		if outgoing_email_account or frappe.conf.get("mail_login"):
			self.send_email_to_employer()

	def validate_duplicate(self):
		if frappe.db.exists("LMS Job Application", {"job": self.job, "user": self.user}):
			frappe.throw(_("You have already applied for this job."))

	def send_email_to_employer(self):
		company_email = frappe.get_value("Job Opportunity", self.job, "company_email_address")
		if company_email:
			args = {
				"full_name": frappe.db.get_value("User", self.user, "full_name"),
				"job_title": self.job_title,
			}
			resume = frappe.get_doc(
				"File",
				{
					"file_url": self.resume,
				},
			)
			for lang, recipients, _cc, _bcc in readers(company_email):
				with in_language(lang):
					subject = _("New Job Applicant")
					frappe.sendmail(
						recipients=recipients,
						subject=subject,
						template="job_application",
						args=args,
						attachments=[
							{
								"fname": resume.file_name,
								"fcontent": resume.get_content(),
							}
						],
						header=[subject, "green"],
						retry=3,
					)
