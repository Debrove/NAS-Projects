##################################################
# Copyright (c) Xuanyi Dong [GitHub D-X-Y], 2019 #
##################################################
import torch
import torch.nn as nn

__all__ = ['OPS', 'ResNetBasicblock', 'SearchSpaceNames']

OPS = {
  'none'         : lambda C_in, C_out, stride, affine, track_running_stats: Zero(C_in, C_out, stride),
  'avg_pool_3x3' : lambda C_in, C_out, stride, affine, track_running_stats: POOLING(C_in, C_out, stride, 'avg', affine, track_running_stats),
  'max_pool_3x3' : lambda C_in, C_out, stride, affine, track_running_stats: POOLING(C_in, C_out, stride, 'max', affine, track_running_stats),
  'nor_conv_7x7' : lambda C_in, C_out, stride, affine, track_running_stats: ReLUConvBN(C_in, C_out, (7,7), (stride,stride), (3,3), (1,1), affine, track_running_stats),
  'nor_conv_3x3' : lambda C_in, C_out, stride, affine, track_running_stats: ReLUConvBN(C_in, C_out, (3,3), (stride,stride), (1,1), (1,1), affine, track_running_stats),
  'nor_conv_1x1' : lambda C_in, C_out, stride, affine, track_running_stats: ReLUConvBN(C_in, C_out, (1,1), (stride,stride), (0,0), (1,1), affine, track_running_stats),
  'dua_sepc_3x3' : lambda C_in, C_out, stride, affine, track_running_stats: DualSepConv(C_in, C_out, (3,3), (stride,stride), (1,1), (1,1), affine, track_running_stats),
  'dua_sepc_5x5' : lambda C_in, C_out, stride, affine, track_running_stats: DualSepConv(C_in, C_out, (5,5), (stride,stride), (2,2), (1,1), affine, track_running_stats),
  'dil_sepc_3x3' : lambda C_in, C_out, stride, affine, track_running_stats:     SepConv(C_in, C_out, (3,3), (stride,stride), (2,2), (2,2), affine, track_running_stats),
  'dil_sepc_5x5' : lambda C_in, C_out, stride, affine, track_running_stats:     SepConv(C_in, C_out, (5,5), (stride,stride), (4,4), (2,2), affine, track_running_stats),
  'skip_connect' : lambda C_in, C_out, stride, affine, track_running_stats: Identity() if stride == 1 and C_in == C_out else FactorizedReduce(C_in, C_out, stride, affine, track_running_stats),
}

CONNECT_NAS_BENCHMARK = ['none', 'skip_connect', 'nor_conv_3x3']
NAS_BENCH_102         = ['none', 'skip_connect', 'nor_conv_1x1', 'nor_conv_3x3', 'avg_pool_3x3']
FULL_SPACE           = ['none', 'skip_connect', 'nor_conv_1x1', 'nor_conv_3x3', 'avg_pool_3x3', 'max_pool_3x3', 'nor_conv_7x7']
DARTS_SPACE           = ['none', 'skip_connect', 'dua_sepc_3x3', 'dua_sepc_5x5', 'dil_sepc_3x3', 'dil_sepc_5x5', 'avg_pool_3x3', 'max_pool_3x3']

SearchSpaceNames = {'connect-nas'  : CONNECT_NAS_BENCHMARK,
                    'aa-nas'       : NAS_BENCH_102,
                    'nas-bench-102': NAS_BENCH_102,
                    'full'         : FULL_SPACE,
                    'darts'        : DARTS_SPACE}


class ReLUConvBN(nn.Module):

  def __init__(self, C_in, C_out, kernel_size, stride, padding, dilation, affine, track_running_stats=True):
    super(ReLUConvBN, self).__init__()
    self.op = nn.Sequential(
      nn.ReLU(inplace=False),
      nn.Conv2d(C_in, C_out, kernel_size, stride=stride, padding=padding, dilation=dilation, bias=False),
      nn.BatchNorm2d(C_out, affine=affine, track_running_stats=track_running_stats)
    )

  def forward(self, x):
    return self.op(x)


class SepConv(nn.Module):

  def __init__(self, C_in, C_out, kernel_size, stride, padding, dilation, affine, track_running_stats=True):
    super(SepConv, self).__init__()
    self.op = nn.Sequential(
      nn.ReLU(inplace=False),
      nn.Conv2d(C_in, C_in, kernel_size=kernel_size, stride=stride, padding=padding, dilation=dilation, groups=C_in,
                bias=False),
      nn.Conv2d(C_in, C_out, kernel_size=1, padding=0, bias=False),
      nn.BatchNorm2d(C_out, affine=affine, track_running_stats=track_running_stats),
    )

  def forward(self, x):
    return self.op(x)


class DualSepConv(nn.Module):

  def __init__(self, C_in, C_out, kernel_size, stride, padding, dilation, affine, track_running_stats=True):
    super(DualSepConv, self).__init__()
    self.op_a = SepConv(C_in, C_in, kernel_size, stride, padding, dilation, affine, track_running_stats)
    self.op_b = SepConv(C_in, C_out, kernel_size, 1, padding, dilation, affine, track_running_stats)

  def forward(self, x):
    x = self.op_a(x)
    x = self.op_b(x)
    return x

class ResNetBasicblock(nn.Module):

  def __init__(self, inplanes, planes, stride, affine=True):
    super(ResNetBasicblock, self).__init__()
    assert stride == 1 or stride == 2, 'invalid stride {:}'.format(stride)
    self.conv_a = ReLUConvBN(inplanes, planes, 3, stride, 1, 1, affine)
    self.conv_b = ReLUConvBN(  planes, planes, 3,      1, 1, 1, affine)
    if stride == 2:
      self.downsample = nn.Sequential(
                           nn.AvgPool2d(kernel_size=2, stride=2, padding=0),
                           nn.Conv2d(inplanes, planes, kernel_size=1, stride=1, padding=0, bias=False))
    elif inplanes != planes:
      self.downsample = ReLUConvBN(inplanes, planes, 1, 1, 0, 1, affine)
    else:
      self.downsample = None
    self.in_dim  = inplanes
    self.out_dim = planes
    self.stride  = stride
    self.num_conv = 2

  def extra_repr(self):
    string = '{name}(inC={in_dim}, outC={out_dim}, stride={stride})'.format(name=self.__class__.__name__, **self.__dict__)
    return string

  def forward(self, inputs):

    basicblock = self.conv_a(inputs)
    basicblock = self.conv_b(basicblock)

    if self.downsample is not None:
      residual = self.downsample(inputs)
    else:
      residual = inputs
    return residual + basicblock


class POOLING(nn.Module):

  def __init__(self, C_in, C_out, stride, mode, affine=True, track_running_stats=True):
    super(POOLING, self).__init__()
    if C_in == C_out:
      self.preprocess = None
    else:
      self.preprocess = ReLUConvBN(C_in, C_out, 1, 1, 0, affine, track_running_stats)
    if mode == 'avg'  : self.op = nn.AvgPool2d(3, stride=stride, padding=1, count_include_pad=False)
    elif mode == 'max': self.op = nn.MaxPool2d(3, stride=stride, padding=1)
    else              : raise ValueError('Invalid mode={:} in POOLING'.format(mode))

  def forward(self, inputs):
    if self.preprocess: x = self.preprocess(inputs)
    else              : x = inputs
    return self.op(x)


class Identity(nn.Module):

  def __init__(self):
    super(Identity, self).__init__()

  def forward(self, x):
    return x


class Zero(nn.Module):

  def __init__(self, C_in, C_out, stride):
    super(Zero, self).__init__()
    self.C_in   = C_in
    self.C_out  = C_out
    self.stride = stride
    self.is_zero = True

  def forward(self, x):
    if self.C_in == self.C_out:
      if self.stride == 1: return x.mul(0.)
      else               : return x[:,:,::self.stride,::self.stride].mul(0.)
    else:
      shape = list(x.shape)
      shape[1] = self.C_out
      zeros = x.new_zeros(shape, dtype=x.dtype, device=x.device)
      return zeros

  def extra_repr(self):
    return 'C_in={C_in}, C_out={C_out}, stride={stride}'.format(**self.__dict__)


class FactorizedReduce(nn.Module):

  def __init__(self, C_in, C_out, stride, affine, track_running_stats):
    super(FactorizedReduce, self).__init__()
    self.stride = stride
    self.C_in   = C_in  
    self.C_out  = C_out  
    self.relu   = nn.ReLU(inplace=False)
    if stride == 2:
      #assert C_out % 2 == 0, 'C_out : {:}'.format(C_out)
      C_outs = [C_out // 2, C_out - C_out // 2]
      self.convs = nn.ModuleList()
      for i in range(2):
        self.convs.append( nn.Conv2d(C_in, C_outs[i], 1, stride=stride, padding=0, bias=False) )
      self.pad = nn.ConstantPad2d((0, 1, 0, 1), 0)
    else:
      raise ValueError('Invalid stride : {:}'.format(stride))
    self.bn = nn.BatchNorm2d(C_out, affine=affine, track_running_stats=track_running_stats)

  def forward(self, x):
    x = self.relu(x)
    y = self.pad(x)
    out = torch.cat([self.convs[0](x), self.convs[1](y[:,:,1:,1:])], dim=1)
    out = self.bn(out)
    return out

  def extra_repr(self):
    return 'C_in={C_in}, C_out={C_out}, stride={stride}'.format(**self.__dict__)


# Auto-ReID: Searching for a Part-Aware ConvNet for Person Re-Identification, ICCV 2019
class PartAwareOp(nn.Module):

  def __init__(self, C_in, C_out, stride, part=4):
    super().__init__()
    self.part   = 4
    self.hidden = C_in // 3
    self.avg_pool = nn.AdaptiveAvgPool2d(1)
    self.local_conv_list = nn.ModuleList()
    for i in range(self.part):
      self.local_conv_list.append(
            nn.Sequential(nn.ReLU(), nn.Conv2d(C_in, self.hidden, 1), nn.BatchNorm2d(self.hidden, affine=True))
            )
    self.W_K = nn.Linear(self.hidden, self.hidden)
    self.W_Q = nn.Linear(self.hidden, self.hidden)

    if stride == 2  : self.last = FactorizedReduce(C_in + self.hidden, C_out, 2)
    elif stride == 1: self.last = FactorizedReduce(C_in + self.hidden, C_out, 1)
    else:             raise ValueError('Invalid Stride : {:}'.format(stride))

  def forward(self, x):
    batch, C, H, W = x.size()
    assert H >= self.part, 'input size too small : {:} vs {:}'.format(x.shape, self.part)
    IHs = [0]
    for i in range(self.part): IHs.append( min(H, int((i+1)*(float(H)/self.part))) )
    local_feat_list = []
    for i in range(self.part):
      feature = x[:, :, IHs[i]:IHs[i+1], :]
      xfeax   = self.avg_pool(feature)
      xfea    = self.local_conv_list[i]( xfeax )
      local_feat_list.append( xfea )
    part_feature = torch.cat(local_feat_list, dim=2).view(batch, -1, self.part)
    part_feature = part_feature.transpose(1,2).contiguous()
    part_K       = self.W_K(part_feature)
    part_Q       = self.W_Q(part_feature).transpose(1,2).contiguous()
    weight_att   = torch.bmm(part_K, part_Q)
    attention    = torch.softmax(weight_att, dim=2)
    aggreateF    = torch.bmm(attention, part_feature).transpose(1,2).contiguous()
    features = []
    for i in range(self.part):
      feature = aggreateF[:, :, i:i+1].expand(batch, self.hidden, IHs[i+1]-IHs[i])
      feature = feature.view(batch, self.hidden, IHs[i+1]-IHs[i], 1)
      features.append( feature )
    features  = torch.cat(features, dim=2).expand(batch, self.hidden, H, W)
    final_fea = torch.cat((x,features), dim=1)
    outputs   = self.last( final_fea )
    return outputs
