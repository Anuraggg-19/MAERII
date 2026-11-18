import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { request, assistantRequest } from "../services/api";
import {
  recommendationCacheKey,
  recommendationEvidence,
} from "../utils/workflow";

const Context = createContext(null);
export const useWorkspace = () => useContext(Context);

export function WorkspaceProvider({ children }) {
  const [materials, setMaterials] = useState([]);
  const [listError, setListError] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [section, setSection] = useState("overview");
  const [product, setProduct] = useState(null);
  const [records, setRecords] = useState({});
  const [pending, setPending] = useState({});
  const [errors, setErrors] = useState({});
  const [capabilities, setCapabilities] = useState(null);
  const [assistantError, setAssistantError] = useState("");
  const cache = useRef({});
  const recommendationCache = useRef(new Map());
  const enhancementCache = useRef(new Map());
  const inFlight = useRef(new Set());
  const setup = useRef(null);
  const selected = useRef(null);
  const mounted = useRef(true);

  function store(id, task, response) {
    const previous = cache.current[id] || {};
    const next = { ...previous, [task]: response };
    if (task === "categories" || task === "market") {
      delete next.recommendations;
      delete next.marketing;
      for (const key of recommendationCache.current.keys())
        if (key.startsWith(id + ":")) recommendationCache.current.delete(key);
      for (const key of enhancementCache.current.keys())
        if (key.startsWith(id + ":")) enhancementCache.current.delete(key);
    }
    cache.current = { ...cache.current, [id]: next };
    if (mounted.current) setRecords(cache.current);
  }
  async function bootstrapAssistant() {
    try {
      const result = await assistantRequest("capabilities");
      if (mounted.current) {
        setCapabilities(result);
        setAssistantError("");
      }
      return result;
    } catch {
      if (mounted.current)
        setAssistantError(
          "The assistant could not connect. You can retry without leaving this page.",
        );
      return null;
    }
  }
  async function loadMaterials() {
    setListLoading(true);
    setListError("");
    try {
      const result = await request("/api/materials");
      if (mounted.current) setMaterials(result.data.materials || []);
    } catch (e) {
      if (mounted.current) setListError(e.message);
    } finally {
      if (mounted.current) setListLoading(false);
    }
  }
  useEffect(() => {
    mounted.current = true;
    setup.current = bootstrapAssistant();
    loadMaterials();
    return () => {
      mounted.current = false;
    };
  }, []);

  async function run(id, task, callback) {
    const key = id + ":" + task;
    if (inFlight.current.has(key)) return null;
    inFlight.current.add(key);
    setPending((p) => ({ ...p, [key]: true }));
    setErrors((p) => ({ ...p, [key]: "" }));
    try {
      await setup.current;
      const response = await callback();
      store(id, task, response);
      return response;
    } catch (e) {
      if (mounted.current) setErrors((p) => ({ ...p, [key]: e.message }));
      return null;
    } finally {
      inFlight.current.delete(key);
      if (mounted.current) setPending((p) => ({ ...p, [key]: false }));
    }
  }
  async function selectMaterial(id) {
    selected.current = id;
    setSelectedId(id);
    setSection("overview");
    setProduct(null);
    // Read-only detail refresh obtains an authorised reference for the current session.
    return run(id, "material", () => request("/api/materials/" + id));
  }
  function navigate(next) {
    setProduct(null);
    setSection(next);
  }
  async function categories(refresh = false) {
    const id = selected.current;
    return run(id, "categories", () =>
      request(
        `/api/materials/${id}/categories${refresh ? "?refresh=true" : ""}`,
        { method: "POST" },
      ),
    );
  }
  async function market() {
    const id = selected.current;
    return run(id, "market", () =>
      request(`/api/materials/${id}/market`, {
        method: "POST",
        timeout: 600000,
      }),
    );
  }
  async function recommend(constraints) {
    const id = selected.current;
    const market = cache.current[id]?.market?.data;
    if (!market) return null;
    const key = recommendationCacheKey(id, constraints, market);
    if (recommendationCache.current.has(key)) {
      const r = recommendationCache.current.get(key);
      store(id, "recommendations", r);
      return r;
    }
    const result = await run(id, "recommendations", () =>
      request(`/api/materials/${id}/recommend`, {
        body: {
          ...constraints,
          market_context: recommendationEvidence(market),
        },
      }),
    );
    if (result) recommendationCache.current.set(key, result);
    return result;
  }
  async function enhance(recommendation) {
    const id = selected.current;
    const market = cache.current[id]?.market?.data || {};
    const key = id + ":" + recommendationCacheKey(id, recommendation, market);
    setProduct(recommendation.product_name);
    if (enhancementCache.current.has(key)) {
      const r = enhancementCache.current.get(key);
      store(id, "marketing", r);
      return r;
    }
    const result = await run(id, "marketing", () =>
      request(`/api/materials/${id}/enhance`, {
        body: {
          recommendation,
          market_context: recommendationEvidence(market),
        },
      }),
    );
    if (result) enhancementCache.current.set(key, result);
    return result;
  }
  async function retryAssistant() {
    setup.current = bootstrapAssistant();
    const result = await setup.current;
    if (result?.enabled && selected.current)
      await run(selected.current, "material", () =>
        request("/api/materials/" + selected.current),
      );
  }
  const current = records[selectedId] || {};
  const material =
    current.material?.data?.material ||
    materials.find((m) => m.mfp_id === selectedId);
  const refs = Object.fromEntries(
    Object.entries(current)
      .filter(([, r]) => r?.ref)
      .map(([k, r]) => [k, r.ref]),
  );
  const context = {
    material_id: selectedId,
    section: product ? "marketing" : section,
    product,
    refs,
  };
  return (
    <Context.Provider
      value={{
        materials,
        material,
        selectedId,
        section,
        navigate,
        product,
        setProduct,
        current,
        context,
        capabilities,
        assistantError,
        retryAssistant,
        listError,
        listLoading,
        loadMaterials,
        selectMaterial,
        categories,
        market,
        recommend,
        enhance,
        busy: (task) => !!pending[selectedId + ":" + task],
        error: (task) => errors[selectedId + ":" + task] || "",
      }}
    >
      {children}
    </Context.Provider>
  );
}
