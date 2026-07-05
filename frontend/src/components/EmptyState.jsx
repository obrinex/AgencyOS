import { motion } from "framer-motion";

export default function EmptyState({ icon: Icon, title, description, action, testId }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      data-testid={testId}
      className="flex flex-col items-center justify-center rounded-xl border border-white/10 bg-surface-1/50 py-20 px-6 text-center"
    >
      {Icon && (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-2 border border-white/10">
          <Icon className="h-6 w-6 text-graphite" />
        </div>
      )}
      <h3 className="font-display text-lg font-semibold text-foreground">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-graphite">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  );
}
