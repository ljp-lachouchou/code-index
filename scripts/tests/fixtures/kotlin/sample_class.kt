package com.example.comment

// ── 接口定义 ────────────────────────────────────────────────────────────────

interface CommentRepository {
    fun findById(id: String): Comment?
    fun findAll(): List<Comment>
    fun save(comment: Comment): Comment
    fun delete(id: String)
}

// ── 数据类 ──────────────────────────────────────────────────────────────────

data class Comment(
    val id: String,
    val content: String,
    val authorId: String,
)

// ── 主服务类 ────────────────────────────────────────────────────────────────

class CommentService(
    private val repository: CommentRepository,
) {

    fun getComment(id: String): Comment? {
        return repository.findById(id)
    }

    fun listComments(): List<Comment> {
        return repository.findAll()
    }

    fun createComment(content: String, authorId: String): Comment {
        val comment = Comment(
            id = generateId(),
            content = content,
            authorId = authorId,
        )
        return repository.save(comment)
    }

    fun deleteComment(id: String) {
        val existing = repository.findById(id)
        if (existing != null) {
            repository.delete(id)
        }
    }

    private fun generateId(): String {
        return java.util.UUID.randomUUID().toString()
    }

    companion object {
        const val MAX_CONTENT_LENGTH = 500
    }
}

// ── 枚举 ────────────────────────────────────────────────────────────────────

enum class CommentStatus {
    ACTIVE,
    DELETED,
    HIDDEN,
}

// ── typealias ────────────────────────────────────────────────────────────────

typealias CommentId = String
