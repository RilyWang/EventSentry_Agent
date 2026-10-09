-- V2 Schema Migration: 事件版本演化 + 证据独立表 + 四时间轴 + 通知

-- ─── 修改 events 表：添加四时间轴和版本控制字段 ───
ALTER TABLE `events`
  ADD COLUMN `eventTime` varchar(32) AFTER `natureLabel`,
  ADD COLUMN `disclosureTime` varchar(32) AFTER `eventTime`,
  ADD COLUMN `crawlTime` varchar(32) AFTER `disclosureTime`,
  ADD COLUMN `expiresAt` varchar(32) AFTER `crawlTime`,
  ADD COLUMN `currentVersionId` bigint unsigned AFTER `expiresAt`;

-- ─── 事件版本表 ───
CREATE TABLE `eventVersions` (
  `id` serial PRIMARY KEY,
  `eventId` varchar(255) NOT NULL,
  `version` int NOT NULL,
  `status` varchar(64) NOT NULL,
  `nature` enum('positive','negative','neutral','risk') NOT NULL,
  `headline` text NOT NULL,
  `timelineSnapshot` json NOT NULL,
  `evidenceSnapshot` json NOT NULL,
  `directionsSnapshot` json NOT NULL,
  `changeType` enum('update','deny','correct','expire') NOT NULL,
  `changeReason` text,
  `createdBy` varchar(64) NOT NULL DEFAULT 'analyst',
  `createdAt` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  INDEX `eventVersions_eventId_idx` (`eventId`),
  INDEX `eventVersions_version_idx` (`eventId`, `version`)
);

-- ─── 原始消息表 ───
CREATE TABLE `rawMessages` (
  `id` serial PRIMARY KEY,
  `ticker` varchar(32) NOT NULL,
  `source` varchar(255) NOT NULL,
  `sourceType` enum('announcement','news','research','interactive','industry') NOT NULL,
  `sourceUrl` text,
  `title` text NOT NULL,
  `content` text,
  `publishTime` varchar(32) NOT NULL,
  `crawlTime` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  `fingerprint` varchar(64) NOT NULL UNIQUE,
  `processed` boolean DEFAULT false NOT NULL,
  `assignedEventId` varchar(255),
  `createdAt` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  INDEX `rawMessages_ticker_idx` (`ticker`),
  INDEX `rawMessages_processed_idx` (`processed`),
  INDEX `rawMessages_assignedEventId_idx` (`assignedEventId`)
);

-- ─── 时间线节点表 ───
CREATE TABLE `timelineNodes` (
  `id` serial PRIMARY KEY,
  `eventId` varchar(255) NOT NULL,
  `date` varchar(32) NOT NULL,
  `label` varchar(64) NOT NULL,
  `summary` text NOT NULL,
  `tier` enum('T0','T1','T2','T3') NOT NULL,
  `isCurrent` boolean DEFAULT false NOT NULL,
  `orderIndex` int NOT NULL DEFAULT 0,
  `createdAt` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  INDEX `timelineNodes_eventId_idx` (`eventId`),
  INDEX `timelineNodes_date_idx` (`eventId`, `date`)
);

-- ─── 证据项表 ───
CREATE TABLE `evidenceItems` (
  `id` serial PRIMARY KEY,
  `eventId` varchar(255) NOT NULL,
  `source` varchar(255) NOT NULL,
  `sourceUrl` text,
  `date` varchar(32) NOT NULL,
  `summary` text NOT NULL,
  `tier` enum('T0','T1','T2','T3') NOT NULL,
  `credibilityScore` decimal(3,2),
  `verified` boolean DEFAULT false NOT NULL,
  `rawMessageId` bigint unsigned,
  `createdAt` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  INDEX `evidenceItems_eventId_idx` (`eventId`),
  INDEX `evidenceItems_tier_idx` (`eventId`, `tier`)
);

-- ─── 演化方向表 ───
CREATE TABLE `eventDirections` (
  `id` serial PRIMARY KEY,
  `eventId` varchar(255) NOT NULL,
  `label` varchar(255) NOT NULL,
  `description` text NOT NULL,
  `probability` varchar(16) NOT NULL,
  `supporting` json NOT NULL,
  `risk` text NOT NULL,
  `createdAt` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  INDEX `eventDirections_eventId_idx` (`eventId`)
);

-- ─── 来源质量表 ───
CREATE TABLE `sourceQuality` (
  `id` serial PRIMARY KEY,
  `sourceName` varchar(255) NOT NULL UNIQUE,
  `sourceType` enum('T0','T1','T2','T3') NOT NULL,
  `totalPredictions` int NOT NULL DEFAULT 0,
  `correctPredictions` int NOT NULL DEFAULT 0,
  `hitRate` decimal(5,4) NOT NULL DEFAULT 0.0000,
  `lastUpdated` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL
);

-- ─── 通知表 ───
CREATE TABLE `notifications` (
  `id` serial PRIMARY KEY,
  `userId` bigint unsigned NOT NULL,
  `eventId` varchar(255) NOT NULL,
  `type` enum('state_transition','evidence_update','denial','correction','expiry') NOT NULL,
  `title` varchar(255) NOT NULL,
  `content` text NOT NULL,
  `read` boolean DEFAULT false NOT NULL,
  `createdAt` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL,
  INDEX `notifications_userId_idx` (`userId`),
  INDEX `notifications_userId_read_idx` (`userId`, `read`),
  INDEX `notifications_eventId_idx` (`eventId`)
);
