import { Route, Routes } from 'react-router-dom';
import Layout from './Layout';
import Cart from './pages/Cart';
import Checkout from './pages/Checkout';
import Home from './pages/Home';
import NotFound from './pages/NotFound';
import Order from './pages/Order';
import Pay from './pages/Pay';
import Product from './pages/Product';
import Shop from './pages/Shop';
import Visit from './pages/Visit';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="shop" element={<Shop />} />
        <Route path="shop/:id" element={<Product />} />
        <Route path="cart" element={<Cart />} />
        <Route path="checkout" element={<Checkout />} />
        <Route path="pay/:token" element={<Pay />} />
        <Route path="orders/:token" element={<Order />} />
        <Route path="visit" element={<Visit />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
