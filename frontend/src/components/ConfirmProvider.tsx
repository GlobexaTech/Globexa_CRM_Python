"use client";

import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  X,
} from "lucide-react";

import {
  createContext,
  ReactNode,
  useContext,
  useRef,
  useState,
} from "react";

export type ConfirmTone =
  | "danger"
  | "primary"
  | "warning";

type ConfirmOptions = {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  tone?: ConfirmTone;
};

type ConfirmState =
  ConfirmOptions & {
    open: boolean;
  };

type ConfirmContextValue = {
  confirm: (
    options: ConfirmOptions
  ) => Promise<boolean>;
};

const ConfirmContext =
  createContext<
    ConfirmContextValue | undefined
  >(undefined);

const initialState: ConfirmState = {
  open: false,
  title: "",
  message: "",
  confirmText: "Confirm",
  cancelText: "Cancel",
  tone: "primary",
};

export function ConfirmProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [state, setState] =
    useState<ConfirmState>(
      initialState
    );

  const resolver = useRef<
    ((value: boolean) => void) | null
  >(null);

  function confirm(
    options: ConfirmOptions
  ): Promise<boolean> {
    return new Promise((resolve) => {
      resolver.current = resolve;

      setState({
        open: true,
        title: options.title,
        message: options.message,
        confirmText:
          options.confirmText ||
          "Confirm",
        cancelText:
          options.cancelText ||
          "Cancel",
        tone:
          options.tone ||
          "primary",
      });
    });
  }

  function finish(
    result: boolean
  ) {
    resolver.current?.(result);
    resolver.current = null;

    setState(initialState);
  }

  return (
    <ConfirmContext.Provider
      value={{ confirm }}
    >
      {children}

      {state.open && (
        <div
          className="globexa-confirm-overlay"
          role="presentation"
          onMouseDown={() =>
            finish(false)
          }
        >
          <div
            className="globexa-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="globexa-confirm-title"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <div className="globexa-confirm-header">
              <div
                className={`globexa-confirm-icon globexa-confirm-icon-${state.tone}`}
              >
                {state.tone ===
                "danger" ? (
                  <AlertTriangle
                    size={20}
                  />
                ) : state.tone ===
                  "warning" ? (
                  <HelpCircle
                    size={20}
                  />
                ) : (
                  <CheckCircle2
                    size={20}
                  />
                )}
              </div>

              <button
                type="button"
                className="globexa-confirm-close"
                onClick={() =>
                  finish(false)
                }
                aria-label="Close confirmation"
              >
                <X size={17} />
              </button>
            </div>

            <h2
              id="globexa-confirm-title"
              className="globexa-confirm-title"
            >
              {state.title}
            </h2>

            <p className="globexa-confirm-message">
              {state.message}
            </p>

            <div className="globexa-confirm-actions">
              <button
                type="button"
                className="globexa-confirm-cancel"
                onClick={() =>
                  finish(false)
                }
              >
                {state.cancelText}
              </button>

              <button
                type="button"
                className={`globexa-confirm-submit globexa-confirm-submit-${state.tone}`}
                onClick={() =>
                  finish(true)
                }
              >
                {state.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const context =
    useContext(ConfirmContext);

  if (!context) {
    throw new Error(
      "useConfirm must be used inside ConfirmProvider."
    );
  }

  return context;
}