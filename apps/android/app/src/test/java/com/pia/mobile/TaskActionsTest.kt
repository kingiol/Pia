package com.pia.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskActionsTest {
    private val approvalActions = setOf(
        "APPROVE", "REJECT", "NO_ACTION", "REQUEST_MORE_RESEARCH", "MARK_AS_WATCH",
    )

    @Test
    fun blockedAndTerminalTasksHaveNoActions() {
        listOf(
            "BLOCKED", "APPROVED", "DONE", "REJECTED", "NO_ACTION", "CANCELLED", "EXPIRED", "UNKNOWN",
        ).forEach { status ->
            assertTrue("$status must not expose task actions", taskActions(status).isEmpty())
        }
    }

    @Test
    fun humanDecisionsAreAvailableOnlyWhileWaitingForApproval() {
        val statuses = listOf(
            "QUEUED", "PLANNING", "RUNNING", "REVIEWING", "PAUSED",
            "WAITING_APPROVAL", "FAILED", "RETRYABLE", "TIMEOUT", "BLOCKED", "NO_ACTION",
        )
        statuses.forEach { status ->
            val actions = taskActions(status, eligible = true, hasSymbol = true).map { it.second }.toSet()
            assertEquals(
                "Approval gate for $status",
                if (status == "WAITING_APPROVAL") approvalActions else emptySet<String>(),
                actions.intersect(approvalActions),
            )
        }
    }
    @Test
    fun approvalAndWatchRequireIndependentCapabilities() {
        fun actions(eligible: Boolean, hasSymbol: Boolean) =
            taskActions("WAITING_APPROVAL", eligible, hasSymbol).map { it.second }.toSet()

        val reviewActions = setOf("REJECT", "NO_ACTION", "REQUEST_MORE_RESEARCH")
        assertEquals(reviewActions, actions(eligible = false, hasSymbol = false))
        assertEquals(reviewActions + "APPROVE", actions(eligible = true, hasSymbol = false))
        assertEquals(reviewActions + "MARK_AS_WATCH", actions(eligible = false, hasSymbol = true))
        assertEquals(approvalActions, actions(eligible = true, hasSymbol = true))
    }
}
