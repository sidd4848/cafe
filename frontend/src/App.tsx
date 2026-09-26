import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { CustomerLayout, RequireCustomer, RequireStaff, StaffLayout } from './components/Layouts';
import { PageLoader } from './components/ui';
import Login from './pages/Login';

const Onboarding = lazy(() => import('./pages/Onboarding'));
const Home = lazy(() => import('./pages/Home'));
const Order = lazy(() => import('./pages/Order'));
const Orders = lazy(() => import('./pages/Orders'));
const OrderStatus = lazy(() => import('./pages/OrderStatus'));
const Discover = lazy(() => import('./pages/Discover'));
const Wait = lazy(() => import('./pages/Wait'));
const Connect = lazy(() => import('./pages/Connect'));
const ConnectChat = lazy(() => import('./pages/ConnectChat'));
const CheckIn = lazy(() => import('./pages/CheckIn'));
const Profile = lazy(() => import('./pages/Profile'));
const StaffBoard = lazy(() => import('./pages/staff/Board'));
const StaffMenu = lazy(() => import('./pages/staff/MenuAdmin'));
const StaffQR = lazy(() => import('./pages/staff/TableQR'));
const StaffTeam = lazy(() => import('./pages/staff/Team'));
const StaffFloor = lazy(() => import('./pages/staff/Floor'));

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/login" element={<Login audience="customer" />} />
        <Route path="/staff/login" element={<Login audience="staff" />} />

        <Route element={<RequireCustomer />}>
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/checkin" element={<CheckIn />} />
          <Route element={<CustomerLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/order" element={<Order />} />
            <Route path="/orders" element={<Orders />} />
            <Route path="/orders/:id" element={<OrderStatus />} />
            <Route path="/discover" element={<Discover />} />
            <Route path="/wait" element={<Wait />} />
            <Route path="/connect" element={<Connect />} />
            <Route path="/connect/c/:id" element={<ConnectChat />} />
            <Route path="/profile" element={<Profile />} />
          </Route>
        </Route>

        <Route path="/staff" element={<RequireStaff />}>
          <Route element={<StaffLayout />}>
            <Route index element={<StaffBoard />} />
            <Route path="floor" element={<StaffFloor />} />
            <Route path="menu" element={<StaffMenu />} />
            <Route path="qr" element={<StaffQR />} />
            <Route path="team" element={<StaffTeam />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
