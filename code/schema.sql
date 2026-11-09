-- 多人共享记账系统 数据库初始化脚本
-- 对应 UML 类图：10 个实体 + 3 个枚举（Role / RecordStatus / LogOpType 用 MySQL ENUM 实现）

CREATE DATABASE IF NOT EXISTS ledger_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ledger_db;

-- 1. 用户（类图：用户）
CREATE TABLE IF NOT EXISTS user (
  user_id    INT AUTO_INCREMENT PRIMARY KEY,
  username   VARCHAR(50) NOT NULL UNIQUE,
  password   VARCHAR(64) NOT NULL COMMENT 'SHA-256 哈希',
  created_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 场景模板（类图：场景模板；预置旅行/合租/家庭三套）
CREATE TABLE IF NOT EXISTS scene_template (
  template_id      INT AUTO_INCREMENT PRIMARY KEY,
  template_type    VARCHAR(20)  NOT NULL UNIQUE COMMENT '旅行/合租/家庭',
  default_category VARCHAR(200) NOT NULL COMMENT '默认类别，逗号分隔',
  settle_method    VARCHAR(50)  NOT NULL COMMENT 'AA均摊/按分摊比例/不结算',
  budget_caliber   VARCHAR(50)  NOT NULL COMMENT '预算口径：总支出'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO scene_template (template_type, default_category, settle_method, budget_caliber) VALUES
  ('旅行', '交通,住宿,餐饮,门票', 'AA均摊',    '总支出'),
  ('合租', '租金,水电,燃气,网费', '按分摊比例', '总支出'),
  ('家庭', '食品,日用品,教育,医疗', '不结算',  '总支出')
ON DUPLICATE KEY UPDATE template_type = template_type;

-- 3. 账本（类图：账本；账本 1--1 场景模板）
CREATE TABLE IF NOT EXISTS ledger (
  ledger_id      INT AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(50) NOT NULL,
  template_id    INT NOT NULL,
  effective_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (template_id) REFERENCES scene_template(template_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 成员关系（类图：成员关系 + Role 枚举）
CREATE TABLE IF NOT EXISTS membership (
  membership_id INT AUTO_INCREMENT PRIMARY KEY,
  ledger_id     INT NOT NULL,
  user_id       INT NOT NULL,
  role          ENUM('创建者','超级管理员','管理员','普通用户') NOT NULL DEFAULT '普通用户',
  join_time     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  visibility_on TINYINT(1) NOT NULL DEFAULT 1 COMMENT '记录可见性：1=对其他成员可见 0=不可见',
  UNIQUE KEY uk_membership (ledger_id, user_id),
  FOREIGN KEY (ledger_id) REFERENCES ledger(ledger_id) ON DELETE CASCADE,
  FOREIGN KEY (user_id)   REFERENCES user(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 预算（类图：预算；账本 1--0..1 预算，预算可选）
CREATE TABLE IF NOT EXISTS budget (
  budget_id INT AUTO_INCREMENT PRIMARY KEY,
  ledger_id INT NOT NULL UNIQUE,
  amount    DECIMAL(12,2) NOT NULL,
  enabled   TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1=启用 0=未启用',
  FOREIGN KEY (ledger_id) REFERENCES ledger(ledger_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 收支记录（类图：收支记录 + RecordStatus 枚举）
CREATE TABLE IF NOT EXISTS ledger_record (
  record_id     INT AUTO_INCREMENT PRIMARY KEY,
  ledger_id     INT NOT NULL,
  submitter_id  INT NOT NULL COMMENT '上传人',
  category      VARCHAR(50)  NOT NULL COMMENT '类别（来自模板默认类别）',
  reason        VARCHAR(200) NOT NULL,
  amount        DECIMAL(12,2) NOT NULL,
  direction     ENUM('收入','支出') NOT NULL DEFAULT '支出' COMMENT '收支方向（金额恒为正，REQ-017）',
  record_time   DATETIME NOT NULL,
  receipt       VARCHAR(200) COMMENT '支付凭证',
  status        ENUM('待审核','已生效','已驳回','已删除') NOT NULL DEFAULT '待审核',
  reject_reason VARCHAR(200) COMMENT '驳回理由',
  FOREIGN KEY (ledger_id)    REFERENCES ledger(ledger_id) ON DELETE CASCADE,
  FOREIGN KEY (submitter_id) REFERENCES user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 分摊明细（类图：分摊明细；收支记录 1 *-- * 分摊明细，组合）
CREATE TABLE IF NOT EXISTS split_item (
  split_id  INT AUTO_INCREMENT PRIMARY KEY,
  record_id INT NOT NULL,
  user_id   INT NOT NULL COMMENT '参与人',
  ratio     FLOAT NOT NULL COMMENT '分摊比例',
  UNIQUE KEY uk_split (record_id, user_id),
  FOREIGN KEY (record_id) REFERENCES ledger_record(record_id) ON DELETE CASCADE,
  FOREIGN KEY (user_id)   REFERENCES user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 操作日志（类图：操作日志 + LogOpType 枚举）
CREATE TABLE IF NOT EXISTS operation_log (
  log_id       INT AUTO_INCREMENT PRIMARY KEY,
  ledger_id    INT NOT NULL,
  op_type      ENUM('加入','删除','修改','审核失败') NOT NULL,
  category     VARCHAR(50) COMMENT '日志类别',
  auditor_id   INT COMMENT '审核人',
  submitter_id INT COMMENT '提交人',
  log_time     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ledger_id)    REFERENCES ledger(ledger_id) ON DELETE CASCADE,
  FOREIGN KEY (auditor_id)   REFERENCES user(user_id),
  FOREIGN KEY (submitter_id) REFERENCES user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. 日志访问授权（类图：日志访问授权；成员 *--* 授权，一次有效）
CREATE TABLE IF NOT EXISTS log_access_grant (
  grant_id       INT AUTO_INCREMENT PRIMARY KEY,
  membership_id  INT NOT NULL,
  grant_admin_id INT NOT NULL COMMENT '授权管理员',
  grant_time     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  used           TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已使用（一次有效）',
  FOREIGN KEY (membership_id)  REFERENCES membership(membership_id) ON DELETE CASCADE,
  FOREIGN KEY (grant_admin_id) REFERENCES user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. 结算（类图：结算；账本 1--* 结算）
CREATE TABLE IF NOT EXISTS settlement (
  settle_id   INT AUTO_INCREMENT PRIMARY KEY,
  ledger_id   INT NOT NULL,
  settle_time DATETIME NOT NULL,
  period      VARCHAR(50) NOT NULL COMMENT '结算周期',
  result      VARCHAR(500) COMMENT '结算结果摘要',
  FOREIGN KEY (ledger_id) REFERENCES ledger(ledger_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
