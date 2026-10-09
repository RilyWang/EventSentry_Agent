export default function Login() {
  const authUrl = `${import.meta.env.VITE_KIMI_AUTH_URL}/api/oauth/authorize?client_id=${import.meta.env.VITE_APP_ID}&redirect_uri=${encodeURIComponent(window.location.origin + "/api/oauth/callback")}&scope=profile&state=${Math.random().toString(36).slice(2)}`;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6 text-center">
        <h1 className="text-2xl font-bold">EventSentry</h1>
        <p className="text-muted-foreground">登录以管理您的持仓和订阅</p>
        <a
          href={authUrl}
          className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          使用 Kimi 账号登录
        </a>
      </div>
    </div>
  );
}
