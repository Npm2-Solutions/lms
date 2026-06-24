import { defineStore } from 'pinia'
import { createResource } from 'frappe-ui'
import { usersStore } from './user'
import { computed, reactive, ref } from 'vue'

export const sessionStore = defineStore('lms-session', () => {
	let { userResource } = usersStore()
	const brand = reactive({})

	function sessionUser() {
		let cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
		let _sessionUser = cookies.get('user_id')
		if (_sessionUser === 'Guest') {
			_sessionUser = null
		} else {
			userResource.reload()
		}
		return _sessionUser
	}

	let user = ref(sessionUser())
	const isLoggedIn = computed(() => !!user.value)

	const logout = createResource({
		url: 'logout',
		onSuccess() {
			userResource.reset()
			user.value = null
			window.location.reload()
		},
	})

	const branding = createResource({
		url: 'lms.lms.api.get_branding',
		cache: 'brand',
		auto: true,
		onSuccess(data) {
			brand.name = data.app_name
			brand.logo = data.app_logo
			brand.favicon =
				data.favicon?.file_url || '/assets/lms/frontend/learning.svg'
		},
	})

	// Worgify Academy mode context: platform mode (client/hub), brand, resolved
	// feature flags + the caller's organization context. Drives mode-gating across
	// the SPA (sidebar items, hub/client-only features).
	const worgify = reactive({
		mode: 'client',
		features: {},
		can_edit_mode: false,
		organization: null,
		is_company_admin: false,
	})
	const modeContext = createResource({
		url: 'lms.worgify.get_mode_context',
		cache: 'worgify_mode_context',
		auto: true,
		onSuccess(data) {
			Object.assign(worgify, data)
		},
	})

	return {
		user,
		isLoggedIn,
		logout,
		brand,
		branding,
		worgify,
		modeContext,
	}
})
