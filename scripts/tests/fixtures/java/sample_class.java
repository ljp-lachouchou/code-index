package com.example.user;

import java.util.List;
import java.util.Optional;

// ── 接口定义 ────────────────────────────────────────────────────────────────

public interface UserRepository {
    Optional<User> findById(String id);
    List<User> findAll();
    User save(User user);
    void delete(String id);
}

// ── 数据类 ──────────────────────────────────────────────────────────────────

class User {
    private final String id;
    private final String name;
    private final String email;

    public User(String id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
}

// ── 服务类 ──────────────────────────────────────────────────────────────────

public class UserService {

    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }

    public Optional<User> getUser(String id) {
        return repository.findById(id);
    }

    public List<User> listUsers() {
        return repository.findAll();
    }

    public User createUser(String name, String email) {
        String id = generateId();
        User user = new User(id, name, email);
        return repository.save(user);
    }

    public void deleteUser(String id) {
        Optional<User> existing = repository.findById(id);
        if (existing.isPresent()) {
            repository.delete(id);
        }
    }

    private String generateId() {
        return java.util.UUID.randomUUID().toString();
    }
}
