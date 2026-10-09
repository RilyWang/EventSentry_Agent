import { useState } from "react";
import { trpc } from "@/providers/trpc";
import { Bell, Check, X } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";

export default function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const utils = trpc.useUtils();

  const { data, isLoading } = trpc.notification.list.useQuery({ unreadOnly: false, limit: 20 });
  const markRead = trpc.notification.markRead.useMutation({
    onSuccess: () => utils.notification.list.invalidate(),
  });
  const markAllRead = trpc.notification.markAllRead.useMutation({
    onSuccess: () => utils.notification.list.invalidate(),
  });

  const unreadCount = data?.unreadCount ?? 0;

  const typeLabel: Record<string, string> = {
    state_transition: "状态更新",
    evidence_update: "新证据",
    denial: "官方否认",
    correction: "更正",
    expiry: "已过期",
  };

  const typeColor: Record<string, string> = {
    state_transition: "bg-blue-500",
    evidence_update: "bg-green-500",
    denial: "bg-red-500",
    correction: "bg-yellow-500",
    expiry: "bg-gray-500",
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button className="relative p-2 rounded-full hover:bg-gray-100">
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span className="absolute top-0 right-0 h-4 w-4 rounded-full bg-red-500 text-[10px] text-white flex items-center justify-center">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full max-w-sm">
        <SheetHeader className="flex flex-row items-center justify-between">
          <SheetTitle>通知中心</SheetTitle>
          {unreadCount > 0 && (
            <Button variant="ghost" size="sm" onClick={() => markAllRead.mutate()}>
              全部已读
            </Button>
          )}
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-80px)] mt-4">
          {isLoading ? (
            <div className="text-center text-muted-foreground py-8">加载中...</div>
          ) : data?.list.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">暂无通知</div>
          ) : (
            <div className="space-y-3">
              {data?.list.map((n) => (
                <div
                  key={n.id}
                  className={`p-3 rounded-lg border ${n.read ? "bg-gray-50" : "bg-white border-l-4 border-l-primary"}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge className={`${typeColor[n.type] || "bg-gray-500"} text-white text-[10px]`}>
                          {typeLabel[n.type] || n.type}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {new Date(n.createdAt).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="text-sm font-medium">{n.title}</p>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{n.content}</p>
                    </div>
                    {!n.read && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={() => markRead.mutate({ id: n.id })}
                      >
                        <Check className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
