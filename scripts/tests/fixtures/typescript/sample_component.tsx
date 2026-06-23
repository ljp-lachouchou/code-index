// @ts-nocheck
// 示例 React Native 组件文件 — 测试 TypeScript / TSX 解析

import React, { useState, useEffect } from "react";
import { View, Text, StyleSheet } from "react-native";

// ── 接口 ──────────────────────────────────────────────────────────────────────

export interface UserProfileProps {
  userId: string;
  displayName: string;
  onFollow?: () => void;
}

// ── 类型别名 ────────────────────────────────────────────────────────────────

export type UserStatus = "active" | "inactive" | "banned";

// ── 枚举 ────────────────────────────────────────────────────────────────────

export enum FollowStatus {
  None = "none",
  Following = "following",
  Followed = "followed",
  Mutual = "mutual",
}

// ── React 组件 ──────────────────────────────────────────────────────────────

export function UserProfileCard({ userId, displayName, onFollow }: UserProfileProps) {
  const [status, setStatus] = useState<UserStatus>("active");
  const [followStatus, setFollowStatus] = useState<FollowStatus>(FollowStatus.None);

  useEffect(() => {
    fetchUserData(userId);
  }, [userId]);

  const handleFollow = () => {
    toggleFollow(userId);
    setFollowStatus(FollowStatus.Following);
    if (onFollow) {
      onFollow();
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.name}>{displayName}</Text>
      <FollowButton onPress={handleFollow} status={followStatus} />
    </View>
  );
}

// ── 辅助函数 ────────────────────────────────────────────────────────────────

function fetchUserData(userId: string): Promise<void> {
  console.log("Fetching user:", userId);
  return Promise.resolve();
}

function toggleFollow(userId: string): boolean {
  return userId.length > 0;
}

// ── 嵌套组件 ────────────────────────────────────────────────────────────────

interface FollowButtonProps {
  onPress: () => void;
  status: FollowStatus;
}

function FollowButton({ onPress, status }: FollowButtonProps) {
  const label = status === FollowStatus.None ? "Follow" : "Following";
  return (
    <Text onPress={onPress} style={styles.button}>
      {label}
    </Text>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { padding: 16 },
  name: { fontSize: 18, fontWeight: "bold" },
  button: { color: "blue", marginTop: 8 },
});
