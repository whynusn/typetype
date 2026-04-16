# TypeType Server API 文档和数据模型

## 1. 项目概述

TypeType Server 是一个基于 Spring Boot 3.2.5 的打字练习应用后端服务，提供用户认证、文本管理、成绩记录和排行榜功能。

### 1.1 技术栈
- **框架**: Spring Boot 3.2.5 + Spring Security + Spring MVC
- **认证**: JWT (io.jsonwebtoken 0.12.6) 双 Token 机制
- **数据库**: MySQL 8.0 + MyBatis 3.0.3
- **数据库迁移**: Flyway
- **构建工具**: Maven
- **Java 版本**: Java 21

### 1.2 项目结构
```
typetype-server/
├── src/main/java/com/typetype/
│   ├── auth/          # 认证模块（JWT 登录/注册）
│   ├── user/          # 用户管理模块
│   ├── text/          # 文本管理模块
│   ├── score/         # 成绩和排行榜模块
│   └── common/        # 公共模块（异常处理、结果封装、安全工具）
├── src/main/resources/
│   ├── application.yml           # 主配置文件
│   ├── application-dev.yml       # 开发环境配置
│   └── db/migration/             # Flyway 数据库迁移脚本
└── pom.xml
```

## 2. API 端点列表

### 2.1 认证模块 (`/api/v1/auth`)

#### 2.1.1 用户注册
- **URL**: `POST /api/v1/auth/register`
- **请求体**: `RegisterDTO`
  ```json
  {
    "username": "string (3-20字符，字母数字下划线)",
    "password": "string (6-30字符)",
    "confirmPassword": "string",
    "nickname": "string (可选，最大64字符)"
  }
  ```
- **响应体**: `Result<UserVO>`
  ```json
  {
    "code": 200,
    "message": "注册成功",
    "data": {
      "id": 1,
      "username": "user123",
      "nickname": "昵称",
      "avatarUrl": null,
      "createdAt": "2026-04-16T01:00:00",
      "updatedAt": "2026-04-16T01:00:00"
    },
    "timestamp": 1713235200000
  }
  ```

#### 2.1.2 用户登录
- **URL**: `POST /api/v1/auth/login`
- **请求体**: `LoginDTO`
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
- **响应体**: `Result<TokenVO>`
  ```json
  {
    "code": 200,
    "message": "登录成功",
    "data": {
      "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "expiresIn": 900,
      "user": {
        "id": 1,
        "username": "user123",
        "nickname": "昵称",
        "avatarUrl": null,
        "createdAt": "2026-04-16T01:00:00",
        "updatedAt": "2026-04-16T01:00:00"
      }
    },
    "timestamp": 1713235200000
  }
  ```

#### 2.1.3 刷新 Token
- **URL**: `POST /api/v1/auth/refresh`
- **请求头**: `Authorization: Bearer <refresh_token>`
- **响应体**: `Result<TokenVO>` (与登录响应相同)

#### 2.1.4 用户登出
- **URL**: `POST /api/v1/auth/logout`
- **请求头**: `Authorization: Bearer <access_token>` (可选)
- **响应体**: `Result<Void>`
  ```json
  {
    "code": 200,
    "message": "登出成功",
    "timestamp": 1713235200000
  }
  ```

### 2.2 用户模块 (`/api/v1/users`)

#### 2.2.1 获取当前用户信息
- **URL**: `GET /api/v1/users/me`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<UserVO>` (与注册响应相同)

#### 2.2.2 根据 ID 获取用户信息（仅管理员）
- **URL**: `GET /api/v1/users/{id}`
- **请求头**: `Authorization: Bearer <access_token>`
- **权限要求**: `ROLE_ADMIN`
- **响应体**: `Result<UserVO>`

### 2.3 文本模块 (`/api/v1/texts`)

#### 2.3.1 获取文本来源目录
- **URL**: `GET /api/v1/texts/catalog`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<List<TextSource>>`
  ```json
  {
    "code": 200,
    "message": "操作成功",
    "data": [
      {
        "id": 1,
        "sourceKey": "cet4",
        "label": "CET-4 词汇",
        "category": "vocabulary",
        "isActive": true,
        "createdAt": "2026-04-16T01:00:00"
      }
    ],
    "timestamp": 1713235200000
  }
  ```

#### 2.3.2 根据来源获取随机文本
- **URL**: `GET /api/v1/texts/source/{sourceKey}`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<Text>`
  ```json
  {
    "code": 200,
    "message": "操作成功",
    "data": {
      "id": 1,
      "sourceId": 1,
      "title": "CET-4 Vocabulary Practice Test",
      "content": "Welcome to the CET-4 vocabulary practice test...",
      "charCount": 150,
      "difficulty": 3,
      "clientTextId": 123456789,
      "createdAt": "2026-04-16T01:00:00"
    },
    "timestamp": 1713235200000
  }
  ```

#### 2.3.3 获取最新文本（每日更新）
- **URL**: `GET /api/v1/texts/latest/{sourceKey}`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<Text>` (同上)

#### 2.3.4 根据 ID 获取文本
- **URL**: `GET /api/v1/texts/{id}`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<Text>` (同上)

#### 2.3.5 根据来源获取文本列表
- **URL**: `GET /api/v1/texts/by-source/{sourceKey}`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<List<Text>>` (文本列表)

#### 2.3.6 根据客户端文本 ID 获取文本
- **URL**: `GET /api/v1/texts/by-client-text-id/{clientTextId}`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<Text>` (单个文本)

#### 2.3.7 上传文本（仅管理员）
- **URL**: `POST /api/v1/texts/upload`
- **请求头**: `Authorization: Bearer <access_token>`
- **权限要求**: `ROLE_ADMIN`
- **请求体**: `UploadTextDTO`
  ```json
  {
    "title": "自定义文本标题",
    "content": "文本内容...",
    "sourceKey": "custom"
  }
  ```
- **响应体**: `Result<Text>` (创建的文本对象)

### 2.4 成绩模块 (`/api/v1`)

#### 2.4.1 提交成绩
- **URL**: `POST /api/v1/scores`
- **请求头**: `Authorization: Bearer <access_token>`
- **请求体**: `SubmitScoreDTO`
  ```json
  {
    "textId": 1,
    "speed": 120.50,
    "effectiveSpeed": 115.30,
    "keyStroke": 8.50,
    "codeLength": 2.1500,
    "accuracyRate": 98.50,
    "charCount": 150,
    "wrongCharCount": 2,
    "duration": 75.50
  }
  ```
- **响应体**: `Result<Void>`
  ```json
  {
    "code": 200,
    "message": "成绩提交成功",
    "timestamp": 1713235200000
  }
  ```

#### 2.4.2 获取用户历史成绩
- **URL**: `GET /api/v1/scores/history?page=1&size=20`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<PageResult<ScoreVO>>`
  ```json
  {
    "code": 200,
    "message": "操作成功",
    "data": {
      "records": [
        {
          "id": 1,
          "textId": 1,
          "textTitle": "CET-4 Vocabulary Practice Test",
          "speed": 120.50,
          "effectiveSpeed": 115.30,
          "keyStroke": 8.50,
          "codeLength": 2.1500,
          "accuracyRate": 98.50,
          "charCount": 150,
          "wrongCharCount": 2,
          "duration": 75.50,
          "createdAt": "2026-04-16T01:00:00"
        }
      ],
      "total": 50,
      "page": 1,
      "size": 20,
      "pages": 3
    },
    "timestamp": 1713235200000
  }
  ```

#### 2.4.3 获取用户在指定文本的历史成绩
- **URL**: `GET /api/v1/texts/{textId}/scores?page=1&size=20`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<PageResult<ScoreVO>>` (同上)

#### 2.4.4 获取文本排行榜
- **URL**: `GET /api/v1/texts/{textId}/leaderboard?page=1&size=50`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<PageResult<LeaderboardVO>>`
  ```json
  {
    "code": 200,
    "message": "操作成功",
    "data": {
      "records": [
        {
          "rank": 1,
          "userId": 1,
          "username": "user123",
          "nickname": "昵称",
          "avatarUrl": null,
          "speed": 150.25,
          "effectiveSpeed": 145.50,
          "keyStroke": 9.20,
          "codeLength": 2.1000,
          "accuracyRate": 99.25,
          "charCount": 150,
          "wrongCharCount": 1,
          "duration": 60.25,
          "createdAt": "2026-04-16T01:00:00"
        }
      ],
      "total": 100,
      "page": 1,
      "size": 50,
      "pages": 2
    },
    "timestamp": 1713235200000
  }
  ```

#### 2.4.5 获取用户在指定文本的最佳成绩
- **URL**: `GET /api/v1/texts/{textId}/best`
- **请求头**: `Authorization: Bearer <access_token>`
- **响应体**: `Result<ScoreVO>` (单个成绩对象或 null)

## 3. 数据模型

### 3.1 用户相关

#### 3.1.1 User (用户实体)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | Long | 用户ID（主键） |
| username | String | 用户名（唯一） |
| password | String | 密码（BCrypt 加密） |
| nickname | String | 昵称 |
| avatarUrl | String | 头像URL |
| role | String | 角色（USER/ADMIN） |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |

#### 3.1.2 UserVO (用户视图对象)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | Long | 用户ID |
| username | String | 用户名 |
| nickname | String | 昵称 |
| avatarUrl | String | 头像URL |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |

#### 3.1.3 RegisterDTO (注册请求)
| 字段名 | 类型 | 校验规则 | 描述 |
|--------|------|----------|------|
| username | String | @NotBlank, @Size(3-20), @Pattern(^[a-zA-Z0-9_]+$) | 用户名 |
| password | String | @NotBlank, @Size(6-30) | 密码 |
| confirmPassword | String | @NotBlank | 确认密码 |
| nickname | String | @Size(max=64) | 昵称（可选） |

#### 3.1.4 LoginDTO (登录请求)
| 字段名 | 类型 | 校验规则 | 描述 |
|--------|------|----------|------|
| username | String | @NotBlank | 用户名 |
| password | String | @NotBlank | 密码 |

### 3.2 认证相关

#### 3.2.1 TokenVO (Token 视图对象)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| accessToken | String | 访问令牌 |
| refreshToken | String | 刷新令牌 |
| expiresIn | Long | 访问令牌过期时间（秒） |
| user | UserVO | 用户信息 |

#### 3.2.2 JwtPayloadDTO (JWT 载荷)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| userId | Long | 用户ID |
| username | String | 用户名 |
| tokenType | String | Token类型（access/refresh） |
| role | String | 角色 |
| iat | Long | 签发时间戳 |
| exp | Long | 过期时间戳 |
| iss | String | 签发者 |
| sub | String | 主题 |

### 3.3 文本相关

#### 3.3.1 Text (文本实体)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | Long | 文本ID（主键） |
| sourceId | Long | 来源ID（外键） |
| title | String | 文本标题 |
| content | String | 文本内容 |
| charCount | Integer | 字符数（冗余字段） |
| difficulty | Integer | 难度等级（0-5） |
| clientTextId | Long | 客户端文本ID（hash值） |
| createdAt | LocalDateTime | 创建时间 |

#### 3.3.2 TextSource (文本来源实体)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | Long | 来源ID（主键） |
| sourceKey | String | 来源标识（如 cet4） |
| label | String | 来源名称 |
| category | String | 分类（vocabulary/article/custom） |
| isActive | Boolean | 是否启用 |
| createdAt | LocalDateTime | 创建时间 |

#### 3.3.3 UploadTextDTO (上传文本请求)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| title | String | 文本标题 |
| content | String | 文本内容 |
| sourceKey | String | 来源标识 |

### 3.4 成绩相关

#### 3.4.1 Score (成绩实体)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | Long | 成绩ID（主键） |
| userId | Long | 用户ID（外键） |
| textId | Long | 文本ID（外键） |
| speed | BigDecimal | 速度（字/分） |
| effectiveSpeed | BigDecimal | 有效速度（字/分） |
| keyStroke | BigDecimal | 击键速度（击/秒） |
| codeLength | BigDecimal | 码长（击/字） |
| accuracyRate | BigDecimal | 准确率（%） |
| charCount | Integer | 字符数 |
| wrongCharCount | Integer | 错误字符数 |
| duration | BigDecimal | 时长（秒） |
| createdAt | LocalDateTime | 创建时间 |
| textTitle | String | 文本标题（关联查询字段） |

#### 3.4.2 SubmitScoreDTO (提交成绩请求)
| 字段名 | 类型 | 校验规则 | 描述 |
|--------|------|----------|------|
| textId | Long | - | 文本ID |
| speed | BigDecimal | @NotNull, @DecimalMin(0) | 速度 |
| effectiveSpeed | BigDecimal | @NotNull, @DecimalMin(0) | 有效速度 |
| keyStroke | BigDecimal | @NotNull, @DecimalMin(0) | 击键速度 |
| codeLength | BigDecimal | @NotNull, @DecimalMin(0) | 码长 |
| accuracyRate | BigDecimal | @NotNull, @DecimalMin(0), @DecimalMax(100) | 准确率 |
| charCount | Integer | @NotNull, @Min(0) | 字符数 |
| wrongCharCount | Integer | @NotNull, @Min(0) | 错误字符数 |
| duration | BigDecimal | @NotNull, @DecimalMin(0) | 时长 |

#### 3.4.3 ScoreVO (成绩视图对象)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| id | Long | 成绩ID |
| textId | Long | 文本ID |
| textTitle | String | 文本标题 |
| speed | BigDecimal | 速度 |
| effectiveSpeed | BigDecimal | 有效速度 |
| keyStroke | BigDecimal | 击键速度 |
| codeLength | BigDecimal | 码长 |
| accuracyRate | BigDecimal | 准确率 |
| charCount | Integer | 字符数 |
| wrongCharCount | Integer | 错误字符数 |
| duration | BigDecimal | 时长 |
| createdAt | LocalDateTime | 创建时间 |

#### 3.4.4 LeaderboardVO (排行榜视图对象)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| rank | Integer | 排名 |
| userId | Long | 用户ID |
| username | String | 用户名 |
| nickname | String | 昵称 |
| avatarUrl | String | 头像URL |
| speed | BigDecimal | 速度 |
| effectiveSpeed | BigDecimal | 有效速度 |
| keyStroke | BigDecimal | 击键速度 |
| codeLength | BigDecimal | 码长 |
| accuracyRate | BigDecimal | 准确率 |
| charCount | Integer | 字符数 |
| wrongCharCount | Integer | 错误字符数 |
| duration | BigDecimal | 时长 |
| createdAt | LocalDateTime | 达成时间 |

### 3.5 通用响应

#### 3.5.1 Result<T> (统一响应)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| code | Integer | 状态码 |
| message | String | 消息 |
| data | T | 数据 |
| timestamp | Long | 时间戳 |

#### 3.5.2 PageResult<T> (分页响应)
| 字段名 | 类型 | 描述 |
|--------|------|------|
| records | List<T> | 数据列表 |
| total | Long | 总记录数 |
| page | Long | 当前页码 |
| size | Long | 每页大小 |
| pages | Long | 总页数 |

#### 3.5.3 ResultCode (状态码枚举)
| 常量 | 值 | 描述 |
|------|----|------|
| SUCCESS | 200 | 操作成功 |
| SYSTEM_ERROR | 10001 | 系统内部异常 |
| PARAM_ERROR | 10002 | 参数校验失败 |
| NOT_FOUND | 10003 | 资源不存在 |
| TOKEN_EXPIRED | 20001 | Token 已过期 |
| TOKEN_INVALID | 20002 | Token 无效 |
| PASSWORD_ERROR | 20003 | 密码错误 |
| USER_NOT_FOUND | 20004 | 用户名不存在 |
| USER_EXISTS | 20005 | 用户名已存在 |
| TEXT_SOURCE_NOT_FOUND | 30001 | 文本来源不存在 |
| TEXT_NOT_FOUND | 30002 | 无可用文本 |
| SCORE_DATA_INVALID | 40001 | 成绩数据异常 |
| SCORE_SUBMIT_TOO_FREQUENT | 40002 | 提交过于频繁 |

## 4. 认证机制

### 4.1 JWT 双 Token 机制
1. **Access Token**: 访问令牌，有效期 15 分钟（900 秒）
2. **Refresh Token**: 刷新令牌，有效期 7 天（604800 秒）

### 4.2 JWT 配置
- **密钥**: 从环境变量 `JWT_SECRET_KEY` 读取，默认值用于开发环境
- **签发者**: `typetype-server`
- **Header**: `Authorization: Bearer <token>`

### 4.3 认证流程
1. 用户登录 → 生成 Access Token + Refresh Token
2. 请求受保护接口 → 在 Header 中携带 Access Token
3. JwtAuthenticationFilter 验证 Token 有效性
4. 验证通过 → 将用户信息存入 SecurityContext
5. Access Token 过期 → 使用 Refresh Token 刷新

### 4.4 安全配置
- **CSRF**: 禁用（JWT API 不需要）
- **白名单**: `/api/v1/auth/**`, `/api/v1/health`, `/error`
- **其他接口**: 需要 JWT 认证
- **密码加密**: BCrypt (strength=10)

## 5. 排行榜算法

### 5.1 排行榜查询逻辑
```sql
SELECT ranked.rank, ranked.userId, ranked.username, ranked.nickname, ranked.avatarUrl,
       ranked.speed, ranked.effectiveSpeed, ranked.keyStroke, ranked.codeLength,
       ranked.accuracyRate, ranked.charCount, ranked.wrongCharCount, ranked.duration,
       ranked.createdAt
FROM (
    SELECT @rank := @rank + 1 AS rank, best.user_id AS userId, u.username, u.nickname,
           u.avatar_url AS avatarUrl, s.speed, s.effective_speed AS effectiveSpeed,
           s.key_stroke AS keyStroke, s.code_length AS codeLength,
           s.accuracy_rate AS accuracyRate, s.char_count AS charCount,
           s.wrong_char_count AS wrongCharCount, s.duration, s.created_at AS createdAt
    FROM (
        SELECT user_id, MAX(speed) AS max_speed
        FROM t_score
        WHERE text_id = #{textId}
        GROUP BY user_id
        ORDER BY max_speed DESC
        LIMIT #{offset}, #{limit}
    ) best
    INNER JOIN t_score s ON s.user_id = best.user_id
        AND s.text_id = #{textId}
        AND s.speed = best.max_speed
    INNER JOIN t_user u ON best.user_id = u.id
    CROSS JOIN (SELECT @rank := #{offset}) r
    ORDER BY s.speed DESC
) ranked
```

### 5.2 算法说明
1. **子查询**: 找出每个用户在指定文本的最高速度（`MAX(speed)`）
2. **分组排序**: 按速度降序排列，分页获取
3. **关联查询**: 关联成绩表和用户表，获取完整信息
4. **排名计算**: 使用 MySQL 变量 `@rank` 实现排名

### 5.3 索引优化
- `idx_text_speed`: (text_id, speed DESC) - 排行榜排序
- `idx_text_user_speed`: (text_id, user_id, speed DESC) - 每用户最佳成绩查询
- `idx_text_user_created`: (text_id, user_id, created_at DESC) - 用户历史成绩查询

## 6. 文本管理

### 6.1 文本来源管理
- **预置来源**: cet4, cet6, essay_classic, code_snippet, jisubei, custom
- **分类**: vocabulary, article, custom, competition
- **状态**: isActive 控制是否启用

### 6.2 文本获取方式
1. **随机获取**: `GET /api/v1/texts/source/{sourceKey}` - 从指定来源随机获取
2. **最新获取**: `GET /api/v1/texts/latest/{sourceKey}` - 获取今日最新文本，无则从外部 API 抓取
3. **列表获取**: `GET /api/v1/texts/by-source/{sourceKey}` - 获取指定来源所有文本
4. **ID 获取**: `GET /api/v1/texts/{id}` - 根据 ID 获取
5. **客户端 ID 获取**: `GET /api/v1/texts/by-client-text-id/{clientTextId}` - 根据 hash ID 获取

### 6.3 外部文本抓取 (SaiWen API)
- **API**: `https://www.jsxiaoshi.com/index.php/Api/Text/getContent`
- **加密**: AES/CBC/NoPadding，密钥和 IV 硬编码
- **请求**: POST JSON，包含加密 payload
- **响应**: 解密后提取文本内容和标题

### 6.4 文本去重机制
- **客户端文本 ID**: `SHA256(sourceKey + ":" + content)` 前8字符 → 十进制 Long → 模 10^9
- **去重逻辑**: 根据 clientTextId 去重，避免重复存储

### 6.5 文本上传 (仅管理员)
- **权限**: 需要 `ROLE_ADMIN`
- **去重**: 根据 clientTextId 去重
- **来源**: 可指定 sourceKey，默认为 custom

## 7. 数据库表结构

### 7.1 t_user (用户表)
```sql
CREATE TABLE t_user (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(32) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    nickname VARCHAR(64),
    avatar_url VARCHAR(512),
    role VARCHAR(32) NOT NULL DEFAULT 'USER',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username)
);
```

### 7.2 t_text_source (文本来源表)
```sql
CREATE TABLE t_text_source (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source_key VARCHAR(64) UNIQUE NOT NULL,
    label VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 7.3 t_text (文本表)
```sql
CREATE TABLE t_text (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    source_id BIGINT NOT NULL,
    title VARCHAR(255),
    content TEXT NOT NULL,
    char_count INT NOT NULL,
    difficulty TINYINT DEFAULT 0,
    client_text_id BIGINT UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES t_text_source(id),
    INDEX idx_source_difficulty (source_id, difficulty),
    INDEX idx_client_text_id (client_text_id)
);
```

### 7.4 t_score (成绩表)
```sql
CREATE TABLE t_score (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    text_id BIGINT,
    speed DECIMAL(8,2) NOT NULL,
    effective_speed DECIMAL(8,2) NOT NULL,
    key_stroke DECIMAL(8,2) NOT NULL,
    code_length DECIMAL(8,4) NOT NULL,
    accuracy_rate DECIMAL(5,2) NOT NULL,
    char_count INT NOT NULL,
    wrong_char_count INT NOT NULL,
    duration DECIMAL(10,2) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES t_user(id),
    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_speed (speed DESC),
    INDEX idx_created_at (created_at),
    INDEX idx_text_speed (text_id, speed DESC),
    INDEX idx_text_user_speed (text_id, user_id, speed DESC),
    INDEX idx_text_user_created (text_id, user_id, created_at DESC)
);
```

## 8. 配置说明

### 8.1 数据库配置
- **URL**: `jdbc:mysql://localhost:3306/typetype`
- **用户名**: root
- **密码**: whynu
- **字符集**: UTF-8

### 8.2 服务器配置
- **端口**: 8080
- **上下文路径**: /

### 8.3 JWT 配置
- **密钥**: 从环境变量 `JWT_SECRET_KEY` 读取
- **Access Token 过期**: 900 秒（15 分钟）
- **Refresh Token 过期**: 604800 秒（7 天）

### 8.4 日志配置
- **根日志级别**: INFO
- **应用日志级别**: DEBUG
- **Spring Security**: DEBUG

## 9. 部署和运行

### 9.1 构建和运行
```bash
# 编译
mvn compile

# 运行
mvn spring-boot:run

# 打包
mvn package

# 运行打包后的 jar
java -jar target/typetype-server-1.0.0.jar
```

### 9.2 环境变量
- `JWT_SECRET_KEY`: JWT 签名密钥（生产环境必须设置）

### 9.3 数据库迁移
- Flyway 自动执行迁移脚本
- 迁移脚本位置: `src/main/resources/db/migration/`
- 命名规范: `V{version}__{description}.sql`

## 10. 错误处理

### 10.1 全局异常处理
- `GlobalExceptionHandler` 处理所有异常
- 返回统一的 `Result` 格式
- 支持参数校验异常、业务异常、JWT 异常等

### 10.2 常见错误码
- **10001**: 系统内部异常
- **10002**: 参数校验失败
- **10003**: 资源不存在
- **20001**: Token 已过期
- **20002**: Token 无效
- **20003**: 密码错误
- **20004**: 用户名不存在
- **20005**: 用户名已存在

## 11. 安全考虑

### 11.1 密码安全
- 使用 BCrypt 加密（strength=10）
- 每次加密生成随机盐值
- 不存储明文密码

### 11.2 JWT 安全
- 双 Token 机制（Access + Refresh）
- Access Token 短期有效（15分钟）
- Refresh Token 长期有效（7天）
- Token Rotation（刷新时生成新 Refresh Token）

### 11.3 接口安全
- CSRF 禁用（JWT API 不需要）
- 白名单机制（登录/注册接口公开）
- 其他接口需要认证
- 基于角色的访问控制（RBAC）

### 11.4 数据安全
- 用户敏感信息不暴露（密码、Token）
- 使用 VO 对象过滤敏感字段
- SQL 注入防护（MyBatis 参数绑定）

## 12. 性能优化

### 12.1 数据库优化
- 合理的索引设计
- 冗余字段减少查询（char_count）
- 分页查询避免全表扫描

### 12.2 缓存考虑
- 预留 Redis 依赖（当前注释）
- 可缓存排行榜、用户信息等热点数据

### 12.3 查询优化
- 排行榜使用子查询 + 变量排名
- 每用户最佳成绩使用 GROUP BY + MAX
- 分页使用 LIMIT offset, size

## 13. 扩展性

### 13.1 水平扩展
- 无状态设计，支持多实例部署
- 数据库可读写分离
- 可引入消息队列处理异步任务

### 13.2 功能扩展
- 支持更多文本来源
- 支持更多排行榜维度（日榜、周榜、月榜）
- 支持用户社交功能（关注、点赞）
- 支持成就系统

### 13.3 监控和运维
- 日志记录详细（DEBUG 级别）
- 异常捕获和处理
- 可集成 APM 监控（如 SkyWalking）

---

**文档版本**: 1.0.0  
**最后更新**: 2026-04-16  
**项目路径**: /home/wangyu/work/typetype-server