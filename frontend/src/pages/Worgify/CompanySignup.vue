<template>
	<div class="max-w-lg mx-auto px-6 py-12">
		<div class="flex items-center gap-3 mb-8">
			<img v-if="brand.favicon" :src="brand.favicon" class="size-9 rounded" />
			<span class="text-xl font-bold text-ink-gray-9">{{ brand.name }}</span>
		</div>

		<!-- not available (client mode or feature off) -->
		<div v-if="!available" class="text-ink-gray-6">
			{{ __('Company registration is not available on this platform.') }}
		</div>

		<!-- success -->
		<div v-else-if="done">
			<h1 class="text-2xl font-bold text-ink-gray-9 mb-2">{{ __('Company registered') }}</h1>
			<p class="text-ink-gray-6 mb-4">
				{{ __("We've emailed {0} to set a password. Your organization join code is:").format(form.admin_email) }}
			</p>
			<div class="font-mono text-lg font-semibold bg-surface-gray-2 rounded-md px-3 py-2 inline-block text-ink-gray-9">
				{{ joinCode }}
			</div>
			<p class="text-ink-gray-5 text-sm mt-3">
				{{ __('Share this code with your employees so they can join — or invite them after signing in.') }}
			</p>
			<a href="/login" class="text-ink-blue-3 mt-5 inline-block">{{ __('Go to sign in') }} →</a>
		</div>

		<!-- form -->
		<div v-else>
			<h1 class="text-2xl font-bold text-ink-gray-9 mb-1">{{ __('Register your company') }}</h1>
			<p class="text-ink-gray-6 mb-6">
				{{ __('Create your organization and an administrator account. You can then invite employees and enrol them in courses.') }}
			</p>
			<div class="space-y-4">
				<FormControl type="text" :label="__('Company name')" v-model="form.organization_name" />
				<FormControl type="text" :label="__('Administrator full name')" v-model="form.admin_full_name" />
				<FormControl type="email" :label="__('Administrator email')" v-model="form.admin_email" />
				<Button variant="solid" class="w-full" :loading="busy" @click="submit">
					{{ __('Register company') }}
				</Button>
				<p v-if="error" class="text-sm text-ink-red-3">{{ error }}</p>
			</div>
		</div>
	</div>
</template>

<script setup>
import { Button, FormControl, call } from 'frappe-ui'
import { ref, reactive, computed } from 'vue'
import { sessionStore } from '@/stores/session'

const session = sessionStore()
const { brand, worgify } = session
const busy = ref(false)
const done = ref(false)
const error = ref('')
const joinCode = ref('')
const form = reactive({ organization_name: '', admin_full_name: '', admin_email: '' })

const available = computed(
	() => worgify.mode === 'hub' && !!worgify.features?.enable_company_self_signup
)

const submit = async () => {
	if (!form.organization_name || !form.admin_email || !form.admin_full_name) {
		error.value = __('All fields are required.')
		return
	}
	busy.value = true
	error.value = ''
	try {
		const res = await call('lms.worgify_groups.register_company', {
			organization_name: form.organization_name,
			admin_email: form.admin_email,
			admin_full_name: form.admin_full_name,
		})
		joinCode.value = res.join_code
		done.value = true
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not register the company.')
	} finally {
		busy.value = false
	}
}
</script>
