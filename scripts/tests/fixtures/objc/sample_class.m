//
//  sample_class.m
//  iOS Demo App
//
//  示例 Objective-C 文件 — 测试 ObjC grammar 解析
//

#import <Foundation/Foundation.h>

#pragma mark - Protocols

/// 用户数据仓库协议
@protocol UserRepositoryProtocol <NSObject>
- (nullable User *)findUserById:(NSString *)userId;
- (BOOL)saveUser:(User *)user;
- (void)deleteUserById:(NSString *)userId;
@end

#pragma mark - Data Model

/// 用户数据模型
@interface User : NSObject

@property (nonatomic, strong) NSString *id;
@property (nonatomic, strong) NSString *name;
@property (nonatomic, strong) NSString *email;
@property (nonatomic, assign) BOOL isActive;

- (instancetype)initWithId:(NSString *)id name:(NSString *)name email:(NSString *)email;
- (NSString *)displayName;

@end

@implementation User

- (instancetype)initWithId:(NSString *)id name:(NSString *)name email:(NSString *)email {
    self = [super init];
    if (self) {
        self.id = id;
        self.name = name;
        self.email = email;
        self.isActive = YES;
    }
    return self;
}

- (NSString *)displayName {
    return [NSString stringWithFormat:@"%@ <%@>", self.name, self.email];
}

@end

#pragma mark - Enum

/// 用户状态
typedef NS_ENUM(NSInteger, UserStatus) {
    UserStatusActive,
    UserStatusInactive,
    UserStatusSuspended
};

#pragma mark - Repository Implementation

/// 内存用户仓库实现
@interface UserRepository : NSObject <UserRepositoryProtocol>

@property (nonatomic, strong) NSMutableDictionary<NSString *, User *> *users;

- (NSArray<User *> *)listAllUsers;

@end

@implementation UserRepository

- (instancetype)init {
    self = [super init];
    if (self) {
        self.users = [NSMutableDictionary dictionary];
    }
    return self;
}

- (nullable User *)findUserById:(NSString *)userId {
    return self.users[userId];
}

- (BOOL)saveUser:(User *)user {
    if (user && user.id) {
        self.users[user.id] = user;
        return YES;
    }
    return NO;
}

- (void)deleteUserById:(NSString *)userId {
    [self.users removeObjectForKey:userId];
}

- (NSArray<User *> *)listAllUsers {
    return [self.users allValues];
}

@end

#pragma mark - Service Layer

/// 用户业务服务
@interface UserService : NSObject

@property (nonatomic, strong) id<UserRepositoryProtocol> repository;

- (instancetype)initWithRepository:(id<UserRepositoryProtocol>)repository;
- (nullable User *)getUser:(NSString *)userId;
- (User *)createUserWithName:(NSString *)name email:(NSString *)email;
- (void)deactivateUser:(NSString *)userId;

@end

@implementation UserService

- (instancetype)initWithRepository:(id<UserRepositoryProtocol>)repository {
    self = [super init];
    if (self) {
        self.repository = repository;
    }
    return self;
}

- (nullable User *)getUser:(NSString *)userId {
    return [self.repository findUserById:userId];
}

- (User *)createUserWithName:(NSString *)name email:(NSString *)email {
    NSString *userId = [[NSUUID UUID] UUIDString];
    User *user = [[User alloc] initWithId:userId name:name email:email];
    [self.repository saveUser:user];
    return user;
}

- (void)deactivateUser:(NSString *)userId {
    User *user = [self.repository findUserById:userId];
    if (user) {
        user.isActive = NO;
        [self.repository saveUser:user];
    }
}

@end

#pragma mark - View Controller

/// 用户列表视图控制器
@interface UserListViewController : NSObject

@property (nonatomic, strong) UserService *service;
@property (nonatomic, strong) NSArray<User *> *users;

- (instancetype)initWithService:(UserService *)service;
- (void)viewDidLoad;
- (void)refreshData;

@end

@implementation UserListViewController

- (instancetype)initWithService:(UserService *)service {
    self = [super init];
    if (self) {
        self.service = service;
    }
    return self;
}

- (void)viewDidLoad {
    [self refreshData];
}

- (void)refreshData {
    self.users = [self.service.repository listAllUsers];
}

@end

#pragma mark - C Functions

NSString *formatUserStatus(UserStatus status) {
    switch (status) {
        case UserStatusActive: return @"Active";
        case UserStatusInactive: return @"Inactive";
        case UserStatusSuspended: return @"Suspended";
        default: return @"Unknown";
    }
}

#pragma mark - Main

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        UserRepository *repo = [[UserRepository alloc] init];
        UserService *service = [[UserService alloc] initWithRepository:repo];

        User *user = [service createUserWithName:@"Alice" email:@"alice@example.com"];
        NSLog(@"Created user: %@", [user displayName]);

        User *found = [service getUser:user.id];
        if (found) {
            NSLog(@"Found: %@", found.name);
        }
    }
    return 0;
}
