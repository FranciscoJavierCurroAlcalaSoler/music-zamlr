import { useState, useEffect, useCallback } from "react";
import type { Collection } from "./types";
import { Alert, Box, Tab, Tabs } from "@mui/material";
import { describeFetchError, fetchCollections } from "./api";
import { DiffView } from "./components/DiffView";
import { CollectionsView } from "./components/CollectionsView";

function App() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(true);
  const [collectionsError, setCollectionsError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  // Promise callbacks rather than async/await, deliberately. This runs from
  // an effect, and react-hooks/set-state-in-effect rejects a setState that an
  // effect can reach synchronously — which, to that rule, is the entire body
  // of an async function. Keeping the await inside fetchCollections (which
  // touches no state) leaves every setState here in a callback, the form the
  // rule asks for. Handlers fired by a click, like runDiff in DiffView, are
  // not effects and keep async/await.
  //
  // Returns the chain so callers can await a refresh and then act on a list
  // that has actually arrived.
  const refreshCollections = useCallback(() => {
    return fetchCollections()
      .then((data) => {
        setCollections(data);
        // Cleared on success rather than at the start of the request, since
        // clearing up front would be the synchronous setState the rule
        // rejects. It also reads better: the error goes away when the
        // problem is fixed, not when we start hoping it is.
        setCollectionsError(null);
      })
      .catch((error: unknown) => {
        setCollectionsError(describeFetchError(error));
      })
      .finally(() => {
        setLoadingCollections(false);
      });
  }, []);

  useEffect(() => {
    refreshCollections();
  }, [refreshCollections]);

  return (
    <Box>
      {collectionsError && (
        <Alert severity="error">Error: {collectionsError}</Alert>
      )}
      <Tabs value={tab} onChange={(_, next) => setTab(next)}>
        <Tab label="Collections" />
        <Tab label="Compare" />
      </Tabs>
      <Box sx={{ display: tab === 0 ? "block" : "none" }}>
        <CollectionsView
          collections={collections}
          loadingCollections={loadingCollections}
          onScanned={refreshCollections}
        />
      </Box>
      <Box sx={{ display: tab === 1 ? "block" : "none" }}>
        <DiffView
          collections={collections}
          loadingCollections={loadingCollections}
        />
      </Box>
    </Box>
  );
}

export default App;
