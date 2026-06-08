"""Backend i18n module for error messages and API responses"""

MESSAGES = {
    "zh": {
        "login_failed": "用户名或密码错误",
        "account_disabled": "账户已被禁用",
        "username_exists": "用户名已存在",
        "user_not_found": "用户不存在",
        "not_authenticated": "未认证",
        "not_admin": "需要管理员权限",
        "template_not_found": "模版不存在",
        "group_not_found": "客群不存在或无权操作",
        "group_no_contacts": "客群中没有联系人",
        "no_send_email": "您尚未配置发送邮箱，请联系管理员",
        "batch_not_found": "批次不存在",
        "record_not_found": "记录不存在",
        "no_permission": "无权操作",
        "no_records_selected": "未选择记录",
        "quota_exhausted": "今日发送配额已用完（限额 {limit} 封），请明天再试",
        "quota_exceeded": "今日剩余配额 {remaining} 封（限额 {limit}，已用 {used}），该客群有 {contacts} 个联系人，超出配额",
        "task_not_found": "任务不存在",
        "time_format_invalid": "时间格式无效",
        "calc_next_run_failed": "计算下次执行时间失败，请检查时间设置",
        "config_saved": "配置已保存",
        "models_saved": "模型列表已保存",
        "restored": "已恢复，该邮箱将重新接收邮件",
        "batch_restored": "已恢复 {count} 条记录",
        "deleted": "已删除",
        "unsub_config_saved": "退订页面配置已保存",
        "test_email_sent": "测试邮件发送成功",
        "ai_not_configured": "未配置 AI 模型，请在系统设置中配置",
        "ai_optimize_failed": "AI 优化失败",
        "ai_evaluate_failed": "AI 评测失败",
        "ai_fix_failed": "获取修复建议失败",
        "missing_token": "缺少 token",
        "invalid_token": "无效的 token",
    },
    "en": {
        "login_failed": "Invalid username or password",
        "account_disabled": "Account has been disabled",
        "username_exists": "Username already exists",
        "user_not_found": "User not found",
        "not_authenticated": "Not authenticated",
        "not_admin": "Admin privileges required",
        "template_not_found": "Template not found",
        "group_not_found": "Group not found or no permission",
        "group_no_contacts": "No contacts in this group",
        "no_send_email": "Sending email not configured, please contact admin",
        "batch_not_found": "Batch not found",
        "record_not_found": "Record not found",
        "no_permission": "No permission",
        "no_records_selected": "No records selected",
        "quota_exhausted": "Daily sending quota exhausted (limit {limit}), please try again tomorrow",
        "quota_exceeded": "Daily remaining quota {remaining} (limit {limit}, used {used}), group has {contacts} contacts, exceeds quota",
        "task_not_found": "Task not found",
        "time_format_invalid": "Invalid time format",
        "calc_next_run_failed": "Failed to calculate next run time, please check time settings",
        "config_saved": "Settings saved",
        "models_saved": "Model list saved",
        "restored": "Restored, this email will receive messages again",
        "batch_restored": "{count} records restored",
        "deleted": "Deleted",
        "unsub_config_saved": "Unsubscribe page config saved",
        "test_email_sent": "Test email sent successfully",
        "ai_not_configured": "AI model not configured, please configure in system settings",
        "ai_optimize_failed": "AI optimization failed",
        "ai_evaluate_failed": "AI evaluation failed",
        "ai_fix_failed": "Failed to get fix suggestions",
        "missing_token": "Missing token",
        "invalid_token": "Invalid token",
    },
}


def t(key: str, lang: str = "zh", **kwargs) -> str:
    msg = MESSAGES.get(lang, MESSAGES["zh"]).get(key) or MESSAGES["zh"].get(key, key)
    if kwargs:
        for k, v in kwargs.items():
            msg = msg.replace("{" + k + "}", str(v))
    return msg


def get_lang_from_header(accept_language: str = "") -> str:
    if not accept_language:
        return "zh"
    if accept_language.lower().startswith("en"):
        return "en"
    return "zh"
