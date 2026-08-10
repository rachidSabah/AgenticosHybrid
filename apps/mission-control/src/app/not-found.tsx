import { Panel, Empty } from "@/components/ui/primitives";

export default function NotFound() {
  return (
    <div className="grid h-dvh place-items-center text-center">
      <Panel title="Page Not Found" subtitle="The route you requested does not exist.">
        <Empty title="404" hint="The page you're looking for doesn't exist or has been moved." />
      </Panel>
    </div>
  );
}