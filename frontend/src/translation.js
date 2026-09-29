import { createResource } from 'frappe-ui'

export default function translationPlugin(app) {
	app.config.globalProperties.__ = translate
	window.__ = translate
	if (!window.translatedMessages) fetchTranslations()
}

// Frappe's signature, __(text, replace, context): a context picks the meaning
// when one English word means two things across the platform ("Jobs" is a job
// board here, customer work orders elsewhere). The catalogue keys a contextual
// entry as "text:context"; without one the bare text is used. `replace` is
// unused — placeholders go through .format().
function translate(message, replace, context) {
	let translatedMessages = window.translatedMessages || {}
	let translatedMessage =
		(context && translatedMessages[`${message}:${context}`]) ||
		translatedMessages[message] ||
		message

	const hasPlaceholders = /{\d+}/.test(message)
	if (!hasPlaceholders) {
		return translatedMessage
	}
	return {
		format: function (...args) {
			return translatedMessage.replace(
				/{(\d+)}/g,
				function (match, number) {
					return typeof args[number] != 'undefined'
						? args[number]
						: match
				}
			)
		},
	}
}

function fetchTranslations(lang) {
	createResource({
		url: 'lms.lms.api.get_translations',
		cache: 'translations',
		auto: true,
		transform: (data) => {
			window.translatedMessages = data
		},
	})
}
