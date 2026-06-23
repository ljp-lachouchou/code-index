//
//  sample_class.swift
//  iOS Demo App
//
//  示例 Swift 文件 — 测试 Swift grammar 解析
//

import Foundation
import UIKit

// MARK: - Protocol

/// 用户数据仓库协议
protocol UserRepositoryProtocol {
    func findUser(byId id: String) -> User?
    func saveUser(_ user: User) -> Bool
    func deleteUser(byId id: String)
}

// MARK: - Data Model

/// 用户数据模型
struct User {
    let id: String
    let name: String
    let email: String
    var isActive: Bool
}

// MARK: - Enum

/// 用户状态枚举
enum UserStatus {
    case active
    case inactive
    case suspended
}

// MARK: - Repository Implementation

/// 用户仓库实现（内存存储）
class UserRepository: UserRepositoryProtocol {

    private var users: [String: User] = [:]

    func findUser(byId id: String) -> User? {
        return users[id]
    }

    func saveUser(_ user: User) -> Bool {
        users[user.id] = user
        return true
    }

    func deleteUser(byId id: String) {
        users.removeValue(forKey: id)
    }

    func listAllUsers() -> [User] {
        return Array(users.values)
    }
}

// MARK: - Service Layer

/// 用户业务服务
class UserService {

    private let repository: UserRepositoryProtocol

    init(repository: UserRepositoryProtocol) {
        self.repository = repository
    }

    func getUser(id: String) -> User? {
        return repository.findUser(byId: id)
    }

    func createUser(name: String, email: String) -> User {
        let id = UUID().uuidString
        let user = User(id: id, name: name, email: email, isActive: true)
        _ = repository.saveUser(user)
        return user
    }

    func deactivateUser(id: String) {
        guard let user = repository.findUser(byId: id) else {
            return
        }
        var updated = user
        updated.isActive = false
        _ = repository.saveUser(updated)
    }
}

// MARK: - ViewController

/// 用户列表视图控制器
class UserListViewController: UIViewController {

    private let service: UserService
    private var users: [User] = []

    init(service: UserService) {
        self.service = service
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        loadUsers()
    }

    private func loadUsers() {
        // 这里应该调用 service 获取用户
        print("Loading users...")
    }

    func refreshData() {
        loadUsers()
    }
}

// MARK: - Extensions

extension User {
    var displayName: String {
        return "\(name) <\(email)>"
    }
}

// MARK: - Global Functions

func formatUserStatus(_ status: UserStatus) -> String {
    switch status {
    case .active:
        return "Active"
    case .inactive:
        return "Inactive"
    case .suspended:
        return "Suspended"
    }
}
