<template>
	<div v-if="org" class="p-6 max-w-4xl mx-auto space-y-6">
		<div class="flex items-start justify-between gap-4">
			<div>
				<h1 class="text-2xl font-bold text-ink-gray-9">{{ org.organization_name }}</h1>
				<p class="text-ink-gray-6 text-sm mt-1">
					<template v-if="!org.is_internal"
						>{{ __('Seats') }}: {{ org.seats_used
						}}<span v-if="org.max_seats"> / {{ org.max_seats }}</span> · </template
					>{{ (org.members || []).length }}
					{{ org.is_internal ? __('people in your workforce') : __('members') }}
				</p>
			</div>
			<div v-if="org.join_code" class="text-right">
				<div class="text-xs text-ink-gray-5">{{ __('Join code') }}</div>
				<div class="font-mono font-semibold text-lg text-ink-gray-9">{{ org.join_code }}</div>
			</div>
		</div>

		<section v-if="org.is_admin && !org.is_internal" class="border rounded-lg p-5 space-y-3">
			<h2 class="font-semibold text-ink-gray-9">{{ __('Invite an employee') }}</h2>
			<div class="flex gap-2 items-end flex-wrap">
				<FormControl type="text" :label="__('Email')" v-model="invite.email" class="min-w-56" />
				<FormControl type="text" :label="__('Full name')" v-model="invite.full_name" class="min-w-56" />
				<Button variant="solid" :loading="busy" @click="doInvite">{{ __('Invite') }}</Button>
			</div>
		</section>

		<section v-if="org.is_admin" class="border rounded-lg p-5 space-y-3">
			<h2 class="font-semibold text-ink-gray-9">{{ __('Enrol members in a course') }}</h2>
			<div class="flex gap-2 items-end flex-wrap">
				<FormControl
					type="select"
					:label="__('Course')"
					:options="courseOptions"
					v-model="enrollCourse"
					class="min-w-72"
				/>
				<Button variant="solid" :loading="busy" :disabled="!selected.length" @click="doEnroll(selected)">
					{{ __('Enrol selected ({0})').format(selected.length) }}
				</Button>
				<Button variant="subtle" :loading="busy" @click="doEnroll(null)">
					{{ __('Enrol all active') }}
				</Button>
			</div>
			<p v-if="enrollMsg" class="text-sm text-ink-gray-6">{{ enrollMsg }}</p>
		</section>

		<section class="border rounded-lg p-5">
			<h2 class="font-semibold text-ink-gray-9 mb-3">{{ __('Members') }}</h2>
			<table class="w-full text-sm">
				<thead>
					<tr class="text-left text-ink-gray-5 border-b">
						<th v-if="org.is_admin" class="py-2 w-8">
							<input type="checkbox" :checked="allSelected" @change="toggleAll" />
						</th>
						<th class="py-2 font-medium">{{ __('Name') }}</th>
						<th class="font-medium">{{ org.is_internal ? __('Login') : __('Email') }}</th>
						<th v-if="!org.is_internal" class="font-medium">{{ __('Role') }}</th>
						<th class="font-medium">{{ __('Status') }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="m in org.members" :key="m.member" class="border-b last:border-0">
						<td v-if="org.is_admin" class="py-2">
							<input
								type="checkbox"
								:value="m.member"
								v-model="selected"
								:disabled="org.is_internal && !m.has_login"
							/>
						</td>
						<td class="py-2 text-ink-gray-8">{{ m.full_name || m.member }}</td>
						<td class="text-ink-gray-6">{{ org.is_internal && !m.has_login ? '—' : m.member }}</td>
						<td v-if="!org.is_internal" class="text-ink-gray-7">
							<select
								v-if="org.is_admin"
								:value="m.member_role"
								@change="(e) => changeRole(m.member, e.target.value)"
								class="border rounded px-1.5 py-0.5 text-sm bg-surface-white"
							>
								<option value="Learner">{{ __('Learner') }}</option>
								<option value="Admin">{{ __('Admin') }}</option>
							</select>
							<span v-else>{{ m.member_role }}</span>
						</td>
						<td class="text-ink-gray-7">{{ m.status }}</td>
					</tr>
					<tr v-if="!(org.members || []).length">
						<td :colspan="org.is_admin ? 5 : 4" class="py-3 text-ink-gray-5">{{ __('No members yet.') }}</td>
					</tr>
				</tbody>
			</table>
		</section>

		<p v-if="error" class="text-sm text-ink-red-3">{{ error }}</p>
	</div>

	<div v-else class="p-10 max-w-md mx-auto text-center space-y-4">
		<p class="text-ink-gray-6">{{ __('You are not part of a learning organization yet.') }}</p>
		<div class="flex gap-2 items-end justify-center">
			<FormControl type="text" :label="__('Join code')" v-model="joinCode" class="min-w-48" />
			<Button variant="solid" :loading="busy" @click="doJoin">{{ __('Join') }}</Button>
		</div>
		<p v-if="error" class="text-sm text-ink-red-3">{{ error }}</p>
	</div>
</template>

<script setup>
import { Button, FormControl, call } from 'frappe-ui'
import { ref, reactive, onMounted, computed } from 'vue'

const org = ref(null)
const busy = ref(false)
const error = ref('')
const enrollMsg = ref('')
const enrollCourse = ref('')
const invite = reactive({ email: '', full_name: '' })
const courses = ref([])
const selected = ref([])
const joinCode = ref('')

const courseOptions = computed(() =>
	courses.value.map((c) => ({ label: c.title || c.name, value: c.name }))
)
const allSelected = computed(() => {
	const ms = (org.value?.members || []).map((m) => m.member)
	return ms.length > 0 && ms.every((m) => selected.value.includes(m))
})
const toggleAll = () => {
	const ms = (org.value?.members || []).map((m) => m.member)
	selected.value = allSelected.value ? [] : ms
}

const load = async () => {
	const data = await call('lms.worgify_groups.get_my_organization')
	org.value = data.organization ? data : null
}

const doJoin = async () => {
	if (!joinCode.value) return
	busy.value = true
	error.value = ''
	try {
		await call('lms.worgify_groups.join_with_code', { join_code: joinCode.value })
		joinCode.value = ''
		await load()
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not join — check the code.')
	} finally {
		busy.value = false
	}
}

onMounted(async () => {
	await load()
	try {
		courses.value = await call('frappe.client.get_list', {
			doctype: 'LMS Course',
			fields: ['name', 'title'],
			limit_page_length: 0,
		})
	} catch (e) {
		courses.value = []
	}
})

const doInvite = async () => {
	if (!invite.email) return
	busy.value = true
	error.value = ''
	try {
		await call('lms.worgify_groups.invite_employee', {
			organization: org.value.organization,
			email: invite.email,
			full_name: invite.full_name,
		})
		invite.email = ''
		invite.full_name = ''
		await load()
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not invite the employee.')
	} finally {
		busy.value = false
	}
}

const doEnroll = async (members) => {
	if (!enrollCourse.value) return
	busy.value = true
	error.value = ''
	enrollMsg.value = ''
	try {
		const params = { organization: org.value.organization, course: enrollCourse.value }
		if (members && members.length) params.members = members
		const res = await call('lms.worgify_groups.enroll_members', params)
		enrollMsg.value = __('Enrolled {0}, already enrolled {1}, blocked (no seats) {2}. Seats used {3}.').format(
			res.enrolled.length,
			res.already_enrolled.length,
			res.blocked_no_seats.length,
			res.seats_used
		)
		selected.value = []
		await load()
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not enrol members.')
	} finally {
		busy.value = false
	}
}

const changeRole = async (member, role) => {
	busy.value = true
	error.value = ''
	try {
		await call('lms.worgify_groups.set_member_role', {
			organization: org.value.organization,
			member,
			role,
		})
		await load()
	} catch (e) {
		error.value = e.messages?.[0] || __('Could not change the role.')
	} finally {
		busy.value = false
	}
}
</script>
