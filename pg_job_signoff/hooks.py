app_name = "pg_job_signoff"
app_title = "PG Job Signoff"
app_publisher = "PinDyn"
app_description = "Job Completion on-site sign-off links for technicians and clients"
app_email = "marcel@pindyn.com"
app_license = "mit"

required_apps = ["frappe_tinyurl"]

doctype_js = {
	"Job Completion": "public/js/job_completion.js"
}

website_route_rules = [
	{"from_route": "/signoff", "to_route": "signoff"},
]

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Job Completion-custom_technician_signoff_short_link",
					"Job Completion-custom_client_signoff_short_link",
					"Job Completion-custom_technician_signed_on",
					"Job Completion-custom_client_signed_on",
				],
			]
		],
	}
]
