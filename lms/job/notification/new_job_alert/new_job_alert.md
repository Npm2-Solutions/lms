{{ _("Hey,") }}

{{ _("A new Job Opportunity has been created.") }} 

<p>{{ _("Company Name") }}: {{ doc.company_name}}</p>
<p>{{ _("Job Title") }}: {{ doc.job_title}}</p>
<p>{{ _("Job Location") }}: {{ doc.location}}</p><br>
<p>{{ _("Job Description") }}: {{ doc.description}}</p><br>

{% set jobs = frappe.utils.get_url() ~ "/app/job-opportunity" %}<p>{{ _("Find all the posted jobs <a href='{0}'>here</a>.").format(jobs) }}</p><br>
