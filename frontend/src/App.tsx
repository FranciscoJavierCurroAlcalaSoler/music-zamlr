import { useState, useEffect, useCallback } from "react";
import type { Collection } from "./types";
import {
  Alert,
  Box,
  CircularProgress,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { describeFetchError, fetchCollections, fetchFormatOrder } from "./api";
import { waitForBackend } from "./startup";
import { logPath } from "./connection";
import { DiffView } from "./components/DiffView";
import { CollectionsView } from "./components/CollectionsView";
import { FormatOrderView } from "./components/FormatOrderView";
import { LogFileNote } from "./components/LogFileNote";

type Startup = "waiting" | "ready" | "failed";

function App() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loadingCollections, setLoadingCollections] = useState(true);
  const [collectionsError, setCollectionsError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);
  const [formatUpdatedAt, setFormatUpdatedAt] = useState<string | null>(null);
  // A count, not a flag: a preview can start while a comparison runs, and the
  // first of the two to end would clear a flag while the other still runs.
  // That is also why the callbacks below use the function form of the setter:
  // a value read when the callback was made would lose one of two overlapping
  // changes.
  const [runningOperations, setRunningOperations] = useState(0);
  const [startup, setStartup] = useState<Startup>("waiting");
  const [startupError, setStartupError] = useState<string | null>(null);

  const startOperation = useCallback(() => {
    setRunningOperations((n) => n + 1);
  }, []);

  const endOperation = useCallback(() => {
    setRunningOperations((n) => n - 1);
  }, []);

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

  // Only the timestamp, because only one question is asked of it here: was
  // the order saved again since a comparison ran? The Settings tab fetches
  // the whole order for itself and reports each save through onSaved.
  //
  // A failure leaves it null and says nothing. This marks a shown comparison
  // as old; it decides nothing about an import, so an unknown order must not
  // put a warning on a comparison that may be perfectly current.
  const refreshFormatOrder = useCallback(() => {
    return fetchFormatOrder()
      .then((data) => {
        setFormatUpdatedAt(data.updated_at);
      })
      .catch(() => {
        setFormatUpdatedAt(null);
      });
  }, []);

  // The shell opens its window before the backend exists, so nothing may ask
  // it anything until it answers. The two refreshes below are gated on that,
  // rather than racing it: a view that fetches behind the splash would
  // produce a second error message for one cause.
  //
  // Promise callbacks, not async/await, for the reason the comment above
  // refreshCollections gives.
  useEffect(() => {
    waitForBackend()
      .then(() => {
        setStartup("ready");
        return Promise.all([refreshCollections(), refreshFormatOrder()]);
      })
      .catch((error: unknown) => {
        setStartup("failed");
        setStartupError(describeFetchError(error));
      });
  }, [refreshCollections, refreshFormatOrder]);

  if (startup === "waiting") {
    return (
      <Stack spacing={2} sx={{ alignItems: "center", marginTop: 8 }}>
        <CircularProgress />
        <Typography>Starting the backend…</Typography>
      </Stack>
    );
  }

  if (startup === "failed") {
    return (
      <Box sx={{ margin: 2 }}>
        <Alert severity="error">{startupError}</Alert>
        <LogFileNote path={logPath()} />
      </Box>
    );
  }

  return (
    <Box>
      {collectionsError && (
        <Alert severity="error">Error: {collectionsError}</Alert>
      )}
      <Tabs value={tab} onChange={(_, next) => setTab(next)}>
        <Tab label="Collections" />
        <Tab label="Compare" />
        <Tab label="Settings" />
      </Tabs>
      <Box sx={{ display: tab === 0 ? "block" : "none" }}>
        <CollectionsView
          collections={collections}
          loadingCollections={loadingCollections}
          onScanned={refreshCollections}
          operationRunning={runningOperations > 0}
        />
      </Box>
      <Box sx={{ display: tab === 1 ? "block" : "none" }}>
        <DiffView
          collections={collections}
          loadingCollections={loadingCollections}
          formatOrderUpdatedAt={formatUpdatedAt}
          onOperationStart={startOperation}
          onOperationEnd={endOperation}
        />
      </Box>
      <Box sx={{ display: tab === 2 ? "block" : "none" }}>
        <FormatOrderView onSaved={refreshFormatOrder} />
        <LogFileNote path={logPath()} />
      </Box>
    </Box>
  );
}

export default App;
