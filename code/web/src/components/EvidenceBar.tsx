import { trpc } from "@/providers/trpc";
import { Badge } from "@/components/ui/badge";
import { Shield, Newspaper, FileText, MessageSquare } from "lucide-react";

interface Props {
  eventId: string;
}

const tierConfig = {
  T0: { label: "公告/监管", color: "bg-emerald-500", icon: <Shield className="h-3 w-3" />, weight: 40 },
  T1: { label: "权威媒体", color: "bg-blue-500", icon: <Newspaper className="h-3 w-3" />, weight: 30 },
  T2: { label: "研报/分析", color: "bg-amber-500", icon: <FileText className="h-3 w-3" />, weight: 20 },
  T3: { label: "传闻/股吧", color: "bg-gray-400", icon: <MessageSquare className="h-3 w-3" />, weight: 10 },
};

export default function EvidenceBar({ eventId }: Props) {
  const { data: evidenceList, isLoading } = trpc.event.evidence.useQuery({ eventId });

  if (isLoading) return <div className="text-sm text-muted-foreground">加载证据链...</div>;

  const counts = {
    T0: evidenceList?.filter((e) => e.tier === "T0").length ?? 0,
    T1: evidenceList?.filter((e) => e.tier === "T1").length ?? 0,
    T2: evidenceList?.filter((e) => e.tier === "T2").length ?? 0,
    T3: evidenceList?.filter((e) => e.tier === "T3").length ?? 0,
  };

  const total = counts.T0 + counts.T1 + counts.T2 + counts.T3;

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-muted-foreground">证据权重</h3>

      {/* 分层进度条 */}
      <div className="h-3 w-full rounded-full overflow-hidden flex">
        {(Object.keys(tierConfig) as Array<keyof typeof tierConfig>).map((tier) => {
          const pct = total > 0 ? (counts[tier] / total) * 100 : 0;
          if (pct === 0) return null;
          return (
            <div
              key={tier}
              className={`${tierConfig[tier].color} h-full transition-all`}
              style={{ width: `${pct}%` }}
              title={`${tierConfig[tier].label}: ${counts[tier]}条`}
            />
          );
        })}
      </div>

      {/* 图例 */}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(tierConfig) as Array<keyof typeof tierConfig>).map((tier) => (
          <div key={tier} className="flex items-center gap-1 text-xs">
            <span className={`inline-block h-2 w-2 rounded-full ${tierConfig[tier].color}`} />
            <span className="text-muted-foreground">{tierConfig[tier].label}</span>
            <Badge variant="secondary" className="text-[10px] h-4 px-1">
              {counts[tier]}
            </Badge>
          </div>
        ))}
      </div>

      {/* 证据列表（前3条） */}
      {evidenceList && evidenceList.length > 0 && (
        <div className="space-y-2 mt-2">
          {evidenceList.slice(0, 3).map((ev) => (
            <div key={ev.id} className="flex items-start gap-2 text-xs p-2 rounded bg-gray-50">
              <span className={`shrink-0 ${tierConfig[ev.tier]?.color.replace("bg-", "text-")}`}>
                {tierConfig[ev.tier]?.icon}
              </span>
              <div className="min-w-0">
                <p className="font-medium truncate">{ev.source}</p>
                <p className="text-muted-foreground line-clamp-2">{ev.summary}</p>
                <p className="text-[10px] text-muted-foreground">{ev.date}</p>
              </div>
            </div>
          ))}
          {evidenceList.length > 3 && (
            <p className="text-xs text-center text-muted-foreground">
              还有 {evidenceList.length - 3} 条证据...
            </p>
          )}
        </div>
      )}
    </div>
  );
}
