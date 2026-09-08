"use client";

import {
  CheckCircle2,
  CircleAlert,
  Info,
  X,
  XCircle,
} from "lucide-react";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useState,
} from "react";

export type ToastType =
  | "success"
  | "error"
  | "warning"
  | "info";

type Toast = {
  id: number;
  title: string;
  message?: string;
  type: ToastType;
};

type ToastContextValue = {
  showToast: (
    title: string,
    message?: string,
    type?: ToastType
  ) => void;
};

const ToastContext =
  createContext<ToastContextValue | undefined>(
    undefined
  );

export function ToastProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback(
    (id: number) => {
      setToasts((current) =>
        current.filter(
          (toast) => toast.id !== id
        )
      );
    },
    []
  );

  const showToast = useCallback(
    (
      title: string,
      message?: string,
      type: ToastType = "success"
    ) => {
      const id =
        Date.now() +
        Math.floor(Math.random() * 10000);

      setToasts((current) => [
        ...current,
        {
          id,
          title,
          message,
          type,
        },
      ]);

      window.setTimeout(() => {
        removeToast(id);
      }, 4000);
    },
    [removeToast]
  );

  return (
    <ToastContext.Provider
      value={{ showToast }}
    >
      {children}

      <div
        className="globexa-toast-container"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <ToastItem
            key={toast.id}
            toast={toast}
            onClose={() =>
              removeToast(toast.id)
            }
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context =
    useContext(ToastContext);

  if (!context) {
    throw new Error(
      "useToast must be used inside ToastProvider."
    );
  }

  return context;
}

function ToastItem({
  toast,
  onClose,
}: {
  toast: Toast;
  onClose: () => void;
}) {
  const Icon =
    toast.type === "success"
      ? CheckCircle2
      : toast.type === "error"
        ? XCircle
        : toast.type === "warning"
          ? CircleAlert
          : Info;

  return (
    <div
      className={`globexa-toast globexa-toast-${toast.type}`}
    >
      <div className="globexa-toast-icon">
        <Icon size={18} />
      </div>

      <div className="min-w-0 flex-1">
        <p className="globexa-toast-title">
          {toast.title}
        </p>

        {toast.message && (
          <p className="globexa-toast-message">
            {toast.message}
          </p>
        )}
      </div>

      <button
        type="button"
        className="globexa-toast-close"
        onClick={onClose}
        aria-label="Close notification"
      >
        <X size={15} />
      </button>
    </div>
  );
}