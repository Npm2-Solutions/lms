<template>
	<SettingsLayout
		:title="__('Platform')"
		:description="__('Platform mode and features. Administrator only.')"
	>
		<div class="flex flex-col gap-6 p-2 text-ink-gray-8">
			<!-- Mode -->
			<div>
				<div class="text-p-base font-medium text-ink-gray-7 mb-1">{{ __('Platform Mode') }}</div>
				<div class="text-p-sm text-ink-gray-5 mb-3">
					{{ __('Client = embedded "Training" inside an worgify bench. Hub = standalone "Worgify Academy".') }}
				</div>
				<div class="flex gap-3">
					<Button
						:variant="worgify.mode === 'client' ? 'solid' : 'subtle'"
						:loading="busy"
						@click="changeMode('Client')"
					>
						{{ __('Client · Training') }}
					</Button>
					<Button
						:variant="worgify.mode === 'hub' ? 'solid' : 'subtle'"
						:loading="busy"
						@click="changeMode('Hub')"
					>
						{{ __('Hub · Worgify Academy') }}
					</Button>
				</div>
				<div class="text-p-sm text-ink-gray-5 mt-2">
					{{ __('Current brand') }}: <b>{{ worgify.brand_name }}</b>
				</div>
			</div>

			<!-- Features (only the current mode's) -->
			<div>
				<div class="text-p-base font-medium text-ink-gray-7 mb-2">{{ __('Features') }}</div>
				<div
					v-for="f in visibleFeatures"
					:key="f.key"
					class="flex items-center justify-between py-2 border-b last:border-0"
				>
					<span>{{ __(f.label) }}</span>
					<Button
						size="sm"
						:variant="worgify.features[f.key] ? 'solid' : 'subtle'"
						:theme="worgify.features[f.key] ? 'green' : 'gray'"
						:loading="busy"
						@click="changeFeature(f.key, !worgify.features[f.key])"
					>
						{{ worgify.features[f.key] ? __('On') : __('Off') }}
					</Button>
				</div>
			</div>

			<p v-if="error" class="text-p-sm text-ink-red-3">{{ error }}</p>
		</div>
	</SettingsLayout>
</template>

<script setup>
import { Button, call } from 'frappe-ui'
import SettingsLayout from '@/components/Layouts/SettingsLayout.vue'
import { computed, ref } from 'vue'
import { sessionStore } from '@/stores/session'

defineProps({ label: { type: String }, description: { type: String } })

const session = sessionStore()
const { worgify } = session
const busy = ref(false)
const error = ref('')

const featureList = [
	{ key: 'enable_company_self_signup', label: 'Company Self-Signup', mode: 'hub' },
	{ key: 'enable_marketplace', label: 'Course Marketplace / Sales', mode: 'hub' },
	{ key: 'enable_distribution', label: 'Distribution to Client Benches', mode: 'hub' },
	{ key: 'enable_stripe_billing', label: 'Automatic (Stripe) Billing', mode: 'hub' },
	{ key: 'enable_competency', label: 'Competency / MRB Bridge', mode: 'client' },
]
const visibleFeatures = computed(() => featureList.filter((f) => f.mode === worgify.mode))

const changeMode = async (m) => {
	busy.value = true
	error.value = ''
	try {
		Object.assign(worgify, await call('lms.worgify.set_mode', { mode: m }))
		session.modeContext?.reload?.()
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not update the mode.')
	} finally {
		busy.value = false
	}
}
const changeFeature = async (flag, val) => {
	busy.value = true
	error.value = ''
	try {
		Object.assign(worgify, await call('lms.worgify.set_feature', { flag, enabled: val ? 1 : 0 }))
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not update the feature.')
	} finally {
		busy.value = false
	}
}
</script>
