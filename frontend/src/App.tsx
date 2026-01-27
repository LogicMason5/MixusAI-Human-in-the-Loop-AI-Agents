import { Routes, Route, Navigate } from "react-router-dom";
import { routes } from "./routes";
import { Navbar, Footer } from "./widgets/layout";
import { StockNews, CryptoNews } from "./pages";

function App() {
  return (
    <>
      <Navbar />

      <main className="pt-0">
        <Routes>
          {/* Main routes */}
          {routes.map(({ path, element }, index) => (
            <Route key={index} path={path} element={element} />
          ))}

          {/* News routes */}
          <Route path="/news">
            <Route path="stock_news" element={<StockNews />} />
            <Route path="crypto_news" element={<CryptoNews />} />
          </Route>

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      </main>

      <Footer />
    </>
  );
}

export default App;
