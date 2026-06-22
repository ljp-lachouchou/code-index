package com.example.notification

import com.example.comment.CommentService
import com.example.comment.Comment

// ── 跨文件依赖 ──────────────────────────────────────────────────────────────
//
// NotificationService 依赖 CommentService，产生跨文件 CALL 边，
// 用于集成测试 find_callers / find_callees / Resolver。

class NotificationService(
    private val commentService: CommentService,
) {

    fun notifyOnNewComment(content: String, authorId: String): Comment {
        val comment = commentService.createComment(content, authorId)
        sendEmail(authorId, comment)
        return comment
    }

    fun notifyOnDelete(commentId: String) {
        commentService.deleteComment(commentId)
        sendPushNotification(commentId)
    }

    private fun sendEmail(userId: String, comment: Comment) {
        // stub
    }

    private fun sendPushNotification(commentId: String) {
        // stub
    }
}
