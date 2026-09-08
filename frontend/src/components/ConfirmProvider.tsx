"use client";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Dialog } from "./Dialog";
export type ConfirmTone = "danger" | "primary" | "warning";
type ConfirmOptions = {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  tone?: ConfirmTone;
};
const ConfirmContext = createContext<
  { confirm: (options: ConfirmOptions) => Promise<boolean> } | undefined
>(undefined);
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((value: boolean) => void) | null>(null);
  useEffect(
    () => () => {
      resolver.current?.(false);
    },
    [],
  );
  function finish(answer: boolean) {
    resolver.current?.(answer);
    resolver.current = null;
    setOptions(null);
  }
  function confirm(value: ConfirmOptions) {
    resolver.current?.(false);
    setOptions(value);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }
  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      <Dialog
        open={Boolean(options)}
        title={options?.title ?? "Confirm action"}
        onClose={() => {
          if (resolver.current) finish(false);
        }}
      >
        <p>{options?.message}</p>
        <div className="crm-actions mt-6">
          <button
            type="button"
            className="crm-secondary"
            autoFocus
            onClick={() => finish(false)}
          >
            {options?.cancelText ?? "Cancel"}
          </button>
          <button
            type="button"
            className={options?.tone === "danger" ? "crm-danger" : "crm-button"}
            onClick={() => finish(true)}
          >
            {options?.confirmText ?? "Confirm"}
          </button>
        </div>
      </Dialog>
    </ConfirmContext.Provider>
  );
}
export function useConfirm() {
  const context = useContext(ConfirmContext);
  if (!context) throw new Error("useConfirm requires ConfirmProvider");
  return context;
}
