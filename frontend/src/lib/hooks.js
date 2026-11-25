import { useCallback, useEffect, useRef, useState } from "react";

/** Run an async loader; returns { data, error, loading, reload, setData }. */
export function useAsync(fn, deps = [], enabled = true) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled });
  const ticket = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(() => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false });
      return Promise.resolve();
    }
    const mine = ++ticket.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    return fnRef.current().then(
      (data) => { if (mine === ticket.current) setState({ data, error: null, loading: false }); },
      (error) => { if (mine === ticket.current) setState({ data: null, error, loading: false }); }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => { run(); }, [run]);

  const setData = useCallback(
    (updater) => setState((s) => ({ ...s, data: typeof updater === "function" ? updater(s.data) : updater })),
    []
  );
  return { ...state, reload: run, setData };
}

/** Wrap a mutating call; returns { run, busy, error, result, reset }. run() resolves undefined on failure. */
export function useAction(fn) {
  const [state, setState] = useState({ busy: false, error: null, result: null });
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const run = useCallback(async (...args) => {
    setState((s) => ({ ...s, busy: true, error: null }));
    try {
      const result = await fnRef.current(...args);
      setState({ busy: false, error: null, result });
      return result;
    } catch (error) {
      setState((s) => ({ busy: false, error, result: s.result }));
      return undefined;
    }
  }, []);
  const reset = useCallback(() => setState({ busy: false, error: null, result: null }), []);
  return { ...state, run, reset };
}

export function useDebounced(value, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
