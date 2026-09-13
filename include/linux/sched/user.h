/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_SCHED_USER_H
#define _LINUX_SCHED_USER_H

#include <linux/uidgid.h>
#include <linux/atomic.h>
#include <linux/refcount.h>
#include <linux/ratelimit.h>
#include <linux/android_kabi.h>

/*
 * Some day this will be a full-fledged user tracking system..
 */
struct user_struct {
	refcount_t __count;	/* reference count */
	atomic_t processes;	/* How many processes does this user have? */
	atomic_t sigpending;	/* How many pending signals does this user have? */
#ifdef CONFIG_FANOTIFY
	atomic_t fanotify_listeners;
#endif
#ifdef CONFIG_EPOLL
	atomic_long_t epoll_watches; /* The number of file descriptors currently watched */
#endif
	/*
	 * 注意：mq_bytes 不在这里定义，而是借用本结构体末尾的 Android KABI
	 * reserve 槽位 1（见下方的 ANDROID_KABI_USE(1, ...)）。原因见那里的注释。
	 */
	unsigned long locked_shm; /* How many pages of mlocked shm ? */
	unsigned long unix_inflight;	/* How many files in flight in unix sockets */
	atomic_long_t pipe_bufs;  /* how many pages are allocated in pipe buffers */

	/* Hash table maintenance information */
	struct hlist_node uidhash_node;
	kuid_t uid;

#if defined(CONFIG_PERF_EVENTS) || defined(CONFIG_BPF_SYSCALL) || \
    defined(CONFIG_NET) || defined(CONFIG_IO_URING)
	atomic_long_t locked_vm;
#endif
#ifdef CONFIG_WATCH_QUEUE
	atomic_t nr_watches;	/* The number of watches this user currently has */
#endif

	/* Miscellaneous per-user rate limit */
	struct ratelimit_state ratelimit;

	/*
	 * CONFIG_POSIX_MQUEUE 需要 mq_bytes（POSIX 消息队列的按用户配额）。
	 * 它不能作为新成员直接加进本结构体：它是全树唯一会改变
	 * struct user_struct 布局的配置项，而 genksyms 会顺着
	 *     struct user_struct *user   (struct cred)
	 *  -> const struct cred *cred    (struct task_struct)
	 * 的指针成员，把本结构体的定义级联进 __crc_init_task。
	 * 一旦 init_task 的 CRC 漂走，原厂 mi_schedule / sched_walt 仍按旧布局算
	 * task_struct 字段偏移，被强行加载后就会踩野地址，开机 0.37s panic。
	 *
	 * 这里改用 ANDROID_KABI_USE() 占用预留槽位：genksyms 在 __GENKSYMS__ 下
	 * 只会看到原来的 u64 android_kabi_reserved1，与不开 mqueue 时逐字
	 * 相同，因此 ABI 指纹不变；而 ipc/mqueue.c 里的 u->mq_bytes 用法
	 * 完全不用改。
	 */
#ifdef CONFIG_POSIX_MQUEUE
	ANDROID_KABI_USE(1, unsigned long mq_bytes);
#else
	ANDROID_KABI_RESERVE(1);
#endif
	ANDROID_KABI_RESERVE(2);
	ANDROID_OEM_DATA_ARRAY(1, 2);
};

extern int uids_sysfs_init(void);

extern struct user_struct *find_user(kuid_t);

extern struct user_struct root_user;
#define INIT_USER (&root_user)


/* per-UID process charging. */
extern struct user_struct * alloc_uid(kuid_t);
static inline struct user_struct *get_uid(struct user_struct *u)
{
	refcount_inc(&u->__count);
	return u;
}
extern void free_uid(struct user_struct *);

#endif /* _LINUX_SCHED_USER_H */
