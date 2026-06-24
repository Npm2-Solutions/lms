<template>
	<div class="p-6 max-w-7xl mx-auto space-y-6">
		<div class="flex items-start justify-between gap-4">
			<div>
				<h1 class="text-2xl font-bold text-ink-gray-9">{{ __('Competency Overview') }}</h1>
				<p class="text-ink-gray-6 mt-1">
					{{ __('Who is certified, expiring, expired, in progress, or has not started — across internal courses and external qualifications.') }}
				</p>
			</div>
			<Button variant="solid" @click="openDialog">{{ __('Record external training') }}</Button>
		</div>

		<!-- summary -->
		<div class="flex gap-2 flex-wrap">
			<div
				v-for="s in statusOrder"
				:key="s"
				class="flex items-center gap-1.5 text-sm border rounded-md px-2.5 py-1"
			>
				<span class="size-2.5 rounded-full" :class="dot[s]" />
				<span class="text-ink-gray-7">{{ __(label[s]) }}</span>
				<span class="font-semibold text-ink-gray-9">{{ data.summary?.[s] || 0 }}</span>
			</div>
		</div>

		<!-- internal: course × member matrix -->
		<div v-if="loading" class="text-ink-gray-5 p-6 text-center">{{ __('Loading…') }}</div>
		<div v-else-if="!data.courses?.length" class="text-ink-gray-6 border rounded-lg p-6 text-center">
			{{ __('No competency-bearing courses yet. Mark a course "Competency-bearing" in its Settings tab.') }}
		</div>
		<div v-else-if="!data.rows?.length" class="text-ink-gray-6 border rounded-lg p-6 text-center">
			{{ __('No members to show.') }}
		</div>
		<div v-else class="border rounded-lg overflow-x-auto">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b">
						<th class="text-left font-medium text-ink-gray-5 p-3 sticky left-0 bg-surface-white">{{ __('Member') }}</th>
						<th v-for="c in data.courses" :key="c.name" class="text-left font-medium text-ink-gray-5 p-3 whitespace-nowrap">
							{{ c.title || c.name }}
						</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in data.rows" :key="row.member" class="border-b last:border-0">
						<td class="p-3 text-ink-gray-8 sticky left-0 bg-surface-white whitespace-nowrap">{{ row.full_name }}</td>
						<td v-for="c in data.courses" :key="c.name" class="p-3">
							<span class="inline-flex items-center gap-1.5 whitespace-nowrap">
								<span class="size-2.5 rounded-full" :class="dot[row.cells[c.name]]" />
								<span class="text-ink-gray-7">{{ __(label[row.cells[c.name]]) }}</span>
							</span>
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- external competencies -->
		<div v-if="data.external?.length">
			<h2 class="font-semibold text-ink-gray-9 mb-2">{{ __('External competencies') }}</h2>
			<div class="border rounded-lg overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="border-b text-left text-ink-gray-5">
							<th class="p-3 font-medium">{{ __('Person') }}</th>
							<th class="p-3 font-medium">{{ __('Qualification') }}</th>
							<th class="p-3 font-medium">{{ __('Body') }}</th>
							<th class="p-3 font-medium">{{ __('Issued') }}</th>
							<th class="p-3 font-medium">{{ __('Expiry') }}</th>
							<th class="p-3 font-medium">{{ __('Status') }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(x, i) in data.external" :key="i" class="border-b last:border-0">
							<td class="p-3 text-ink-gray-8">{{ x.personnel }}</td>
							<td class="p-3 text-ink-gray-7">{{ x.title }}</td>
							<td class="p-3 text-ink-gray-6">{{ x.issuing_body }}</td>
							<td class="p-3 text-ink-gray-6">{{ x.issue_date }}</td>
							<td class="p-3 text-ink-gray-6">{{ x.expiry_date }}</td>
							<td class="p-3">
								<span class="inline-flex items-center gap-1.5">
									<span class="size-2.5 rounded-full" :class="dot[x.status]" />
									<span class="text-ink-gray-7">{{ __(label[x.status]) }}</span>
								</span>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>

		<Dialog v-model="showDialog" :options="{ title: __('Record external training') }">
			<template #body-content>
				<div class="space-y-3">
					<Link doctype="Personnel" :label="__('Personnel')" v-model="form.personnel" :placeholder="__('Select person')" />
					<FormControl type="text" :label="__('Title / competency')" v-model="form.title" :placeholder="__('e.g. ISO 9606-1 Welder Qualification')" />
					<FormControl type="text" :label="__('Issuing body')" v-model="form.issuing_body" :placeholder="__('e.g. TÜV')" />
					<div class="flex gap-3">
						<FormControl type="date" :label="__('Issue date')" v-model="form.issue_date" class="flex-1" />
						<FormControl type="date" :label="__('Expiry date')" v-model="form.expiry_date" class="flex-1" />
					</div>
					<FormControl type="text" :label="__('Regulatory reference')" v-model="form.regulatory_reference" :placeholder="__('e.g. ISO 9606-1')" />
					<Button variant="solid" class="w-full" :loading="saving" @click="recordExternal">{{ __('Save record') }}</Button>
					<p v-if="error" class="text-sm text-ink-red-3">{{ error }}</p>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { call, Button, FormControl, Dialog } from 'frappe-ui'
import Link from '@/components/Controls/Link.vue'
import { reactive, ref, onMounted } from 'vue'

const data = reactive({ courses: [], rows: [], summary: {}, external: [] })
const loading = ref(true)
const showDialog = ref(false)
const saving = ref(false)
const error = ref('')
const emptyForm = () => ({ personnel: '', title: '', issuing_body: '', issue_date: '', expiry_date: '', regulatory_reference: '' })
const form = reactive(emptyForm())

const statusOrder = ['certified', 'expiring', 'expired', 'in_progress', 'not_started']
const label = {
	certified: 'Certified',
	expiring: 'Expiring',
	expired: 'Expired',
	in_progress: 'In progress',
	not_started: 'Not started',
}
const dot = {
	certified: 'bg-surface-green-3',
	expiring: 'bg-surface-amber-3',
	expired: 'bg-surface-red-3',
	in_progress: 'bg-surface-blue-3',
	not_started: 'bg-surface-gray-4',
}

const load = async () => {
	Object.assign(data, await call('lms.worgify_competency.get_competency_overview'))
}
onMounted(async () => {
	try {
		await load()
	} finally {
		loading.value = false
	}
})

const openDialog = () => {
	Object.assign(form, emptyForm())
	error.value = ''
	showDialog.value = true
}
const recordExternal = async () => {
	if (!form.personnel || !form.title || !form.issue_date) {
		error.value = __('Personnel, title and issue date are required.')
		return
	}
	saving.value = true
	error.value = ''
	try {
		await call('lms.worgify_competency.record_external_training', { ...form })
		showDialog.value = false
		await load()
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not save the record.')
	} finally {
		saving.value = false
	}
}
</script>
