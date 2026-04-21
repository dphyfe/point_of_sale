import { Routes, Route } from "react-router-dom";
import Layout from "./layout";
import { PoListPage } from "../features/purchase-orders/PoListPage";
import { PoDetailPage } from "../features/purchase-orders/PoDetailPage";
import { PoCreatePage } from "../features/purchase-orders/PoCreatePage";
import { ReceivePage } from "../features/receiving/ReceivePage";
import { SerialLookupPage } from "../features/inventory-lookup/SerialLookupPage";
import { InventoryByLocationPage } from "../features/inventory-lookup/InventoryByLocationPage";
import { ReturnPage } from "../features/returns/ReturnPage";
import { VendorRmaPage } from "../features/returns/VendorRmaPage";
import { CountSessionListPage } from "../features/counts/CountSessionListPage";
import { CountSessionCreatePage } from "../features/counts/CountSessionCreatePage";
import { CountingUI } from "../features/counts/CountingUI";
import { VarianceReviewPage } from "../features/counts/VarianceReviewPage";
import { TransferListPage } from "../features/transfers/TransferListPage";
import { TransferCreatePage } from "../features/transfers/TransferCreatePage";
import { TransferShipPage } from "../features/transfers/TransferShipPage";
import { TransferReceivePage } from "../features/transfers/TransferReceivePage";

export default function App() {
    return (
        <Layout>
            <Routes>
                <Route path="/" element={<PoListPage />} />
                <Route path="/pos" element={<PoListPage />} />
                <Route path="/pos/new" element={<PoCreatePage />} />
                <Route path="/pos/:id" element={<PoDetailPage />} />
                <Route path="/receive/:poId" element={<ReceivePage />} />
                <Route path="/lookup/serial" element={<SerialLookupPage />} />
                <Route path="/lookup/balance" element={<InventoryByLocationPage />} />
                <Route path="/returns" element={<ReturnPage />} />
                <Route path="/returns/rma" element={<VendorRmaPage />} />
                <Route path="/counts" element={<CountSessionListPage />} />
                <Route path="/counts/new" element={<CountSessionCreatePage />} />
                <Route path="/counts/:id/enter" element={<CountingUI />} />
                <Route path="/counts/:id/variance" element={<VarianceReviewPage />} />
                <Route path="/transfers" element={<TransferListPage />} />
                <Route path="/transfers/new" element={<TransferCreatePage />} />
                <Route path="/transfers/:id/ship" element={<TransferShipPage />} />
                <Route path="/transfers/:id/receive" element={<TransferReceivePage />} />
            </Routes>
        </Layout>
    );
}
