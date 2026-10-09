import { trpc } from "@/providers/trpc";
import { Badge } from "@/components/ui/badge";
import { Clock, ArrowRight, RotateCcw, AlertTriangle, CheckCircle } from "lucide-react";

interface Props {
  eventId: string;
}

export default function EventVersionTimeline({ eventId }: Props) {
  const { data: versions, isLoading } = trpc.event.versions.useQuery({ eventId });

  if (isLoading) return <div className="text-sm text-muted-foreground">加载版本历史...</div>;
  if (!versions?.length) return <div className="text-sm text-muted-foreground">暂无版本记录</div>;

  const changeTypeConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    update: { label: "更新", color: "bg-blue-100 text-blue-700", icon: <Clock className="h-3 w-3" /> },
    deny: { label: "否认", color: "bg-red-100 text-red-700", icon: <AlertTriangle className="h-3 w-3" /> },
    correct: { label: "更正", color: "bg-yellow-100 text-yellow-700", icon: <RotateCcw className="h-3 w-3" /> },
    expire: { label: "过期", color: "bg-gray-100 text-gray-700", icon: <CheckCircle className="h-3 w-3" /> },
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-muted-foreground">版本演化</h3>
      <div className="relative pl-4 border-l-2 border-gray-200 space-y-4">
        {versions.map((v, i) => {
          const config = changeTypeConfig[v.changeType] || changeTypeConfig.update;
          const isLatest = i === 0;

          return (
            <div key={v.id} className="relative">
              {/* 节点圆点 */}
              <div
                className={`absolute -left-[21px] top-1 h-3 w-3 rounded-full border-2 ${
                  isLatest ? "bg-primary border-primary" : "bg-white border-gray-300"
                }`}
              />

              <div className={`p-3 rounded-lg border ${isLatest ? "bg-primary/5 border-primary/20" : "bg-gray-50"}`}>
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className={`${config.color} flex items-center gap-1 text-[10px]`}>
                    {config.icon}
                    {config.label}
                  </Badge>
                  <span className="text-xs text-muted-foreground">v{v.version}</span>
                  {isLatest && <Badge className="bg-primary text-white text-[10px]">当前</Badge>}
                </div>

                <p className="text-sm font-medium">{v.headline}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  状态：{v.status} · {v.natureLabel}
                </p>
                {v.changeReason && (
                  <p className="text-xs text-muted-foreground mt-1">原因：{v.changeReason}</p>
                )}
                <p className="text-[10px] text-muted-foreground mt-2">
                  {new Date(v.createdAt).toLocaleString()}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
