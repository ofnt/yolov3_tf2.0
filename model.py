import tensorflow as tf
from tensorflow.keras import Model
from tensorflow.keras.regularizers import l2
from anchors_constants import anchors, anchor_masks
from tensorflow.keras.layers import (BatchNormalization, Add, Concatenate, Conv2D,
                                     Input, LeakyReLU, UpSampling2D, Layer, ZeroPadding2D)
from utils import yolo_boxes, yolo_nms, getFinalYoloBoxes

class DarknetConv(Layer):
    """Initialize a Darknet convolution layer

    Args:
        Layer: Subclassing from Keras layer
        
    Returns:
        Tensor: Returns a tensors of shape (batch_size, grid, grid, featuremaps)
    """
    def __init__(self, filters, kernel_size, strides=1, batch_norm=True, name=''):
        super().__init__(name=name)
        
        self.filters = filters
        self.kernel_size = kernel_size
        self.strides = strides
        self.batch_norm = batch_norm

        ## Layers
        ## .variables, .trainable, .name    
    
    def build(self, input_shape):
        self.conv = Conv2D(filters=self.filters, kernel_size=self.kernel_size, 
                           strides=self.strides, 
                           padding='same' if self.strides == 1 else 'valid', 
                           use_bias=not self.batch_norm, # Bias will get subtracted out during normalization. Batch norm will compute the mean of Z(i) 
                           kernel_regularizer=l2(0.0005))
        if (self.batch_norm):
            self.bn_layer = BatchNormalization()
#        super().build(input_shape) # dc = DarknetConv(..) dc(tf.ones(...)) automatically build 

    def call(self, x):
        """
        Important:
            Need to determine the input shape of the first layer before the chain
            can be propagated to the future layers
        """
#        x = inputs = Input(x.shape[1:]) # (416, 416, 3) Don't pass in batch_size
        print("DarknetConv:", x.shape)
        print("DarknetConv:", x)
        if self.strides != 1:
            x = ZeroPadding2D(((1,0), (1,0)))(x) # top left half-padding
        x = self.conv(x)
        if self.batch_norm:
            x = self.bn_layer(x)
            x = LeakyReLU(alpha=0.1)(x)            
        return x

class DarknetResidual(Layer):
    """Initialize a Darknet Residual layer

    Args:
        Layer: Subclassing from Keras layer
        
    Returns:
        Tensor: Returns a tensors of shape (batch_size, grid, grid, featuremaps)
    """
    def __init__(self, name=''):
        super().__init__(name=name)
        
        
    def build(self, input_shape):
        # build is that it enables late variable creation based on the shape of the inputs the layer will operate on
        self.conv_1 = DarknetConv(filters=int(input_shape[-1]) // 2, kernel_size=1)
        self.conv_2 = DarknetConv(filters=int(input_shape[-1]), kernel_size=3)        
    def call(self, x):
        prev = x
        x = self.conv_1(x)
        x = self.conv_2(x)
        x = Add()([prev, x])
        print("Residual x", x)
        return x

class DarknetBlock(Model):
    """Initialize a Darknet Block which consists a stack or multiple stack 
       of convolution and residual layers

    Args:
        Layer: Subclassing from Keras Model
        
    Returns:
        Tensor: Returns a tensors of shape (batch_size, grid, grid, featuremaps)
    """
    def __init__(self, no_blocks, name=''):
        super().__init__(name=name)
        self.no_blocks = no_blocks        
        self.residual = [DarknetResidual() for _ in range(no_blocks)]
        
    def call(self, x):
        # Forward propagation of all residuals in a block
        for layer in self.residual:
            x = layer(x)
        return x

class Darknet(Model):
    """Initialize the feature extractor Darknet which consists of 52 convolution layers.
    
    Args:
        Layer: Subclassing from Keras Model
        
    Returns:
        Tensor: Returns a tensors of shape (batch_size, grid, grid, featuremaps)
    """
    def __init__(self, name=''):
        super().__init__(name=name)
        self.dc1 = DarknetConv(32, 3, 1, True, name='conv_0')
        self.dc2 = DarknetConv(64, 3, 2, True, name='conv_1')
        self.darknet_block_1_1 = DarknetBlock(1, name='residual_blk_1')
        
        self.dc3 = DarknetConv(128, 3, 2, True, name='conv_4')
        self.darknet_block_2_2 = DarknetBlock(2, name='residual_blk_2')
        
        self.dc4 = DarknetConv(256, 3, 2, True, name='conv_9')
        self.darknet_block_3_8 = DarknetBlock(8, name='residual_blk_3')
        
        self.dc5 = DarknetConv(512, 3, 2, True, name='conv_26')
        self.darknet_block_4_8 = DarknetBlock(8, name='residual_blk_4')
        
        self.dc6 = DarknetConv(1024, 3, 2, True, name='conv_43')
        self.darknet_block_5_4 = DarknetBlock(4, name='residual_blk_5')
    
#    def build(self, input_shape):
#        print(input_shape)
#        super().build(input_shape) # Need this to infer shapes from model.build((1,416,416,3))
        
    def call(self, x):
        """
        Important:
            Need to determine the input shape of the first layer before the chain
            can be propagated to the future layers. (For debugging and visualization of the architecture.)
        """
#        x = inputs = Input(x.shape[1:]) # (416, 416, 3) Don't pass in batch_size
#        print(inputs)
#        x = inputs = Input([416, 416, 3])
        inputs = x
        x = self.dc1(x)
        x = self.dc2(x)
        x = self.darknet_block_1_1(x)
        
        x = self.dc3(x)
        x = self.darknet_block_2_2(x)
        
        x = self.dc4(x)
        x = x_36 = self.darknet_block_3_8(x)
        
        x = self.dc5(x)
        x = x_61 = self.darknet_block_4_8(x)
        
        x = self.dc6(x)
        x = self.darknet_block_5_4(x)
        
        
        return (inputs, x_36, x_61, x)

class YoloConv(Model): # TODO create a class subclassing keras.model to wrap YoloConv and YoloOutput together 
    """Initialize the Yolo convolutions layer after the Darknet feature extractor.
    
    Args:
        Layer: Subclassing from Keras Model
        
    Returns:
        Tensor: Returns a tensors of shape (batch_size, grid, grid, featuremaps)
    """ 
    def __init__(self, filters, isConcat=False, name=''):
        super().__init__(name=name) # name = 'yolo_conv'
        self.filters = filters
        self.isConcat = isConcat

#        self.upsampling2d = UpSampling2D(2)
#        self.concatenate = Concatenate()([x, x_skip])
        
    def build(self, input_shape):
        if (self.isConcat):
            self.yolo_conv_prev = DarknetConv(self.filters, 1, name='yolo_conv_prev')
        self.yolo_conv_1 = DarknetConv(self.filters, 1, name='yolo_conv_1')
        self.yolo_conv_2 = DarknetConv(self.filters * 2, 3, name='yolo_conv_2')
        self.yolo_conv_3 = DarknetConv(self.filters, 1, name='yolo_conv_3')
        self.yolo_conv_4 = DarknetConv(self.filters * 2, 3, name='yolo_conv_4')
        self.yolo_conv_5 = DarknetConv(self.filters, 1, name='yolo_conv_5')
        
            
    def call(self, x):
        # first YOLO layer 13x13x1024
#        x = self.yolo_conv
#        x = self.darknet(x)
        if type(x) is tuple: # (x, x_61) or (x, x_36)
            # first x is (None, 13, 13, 512), x_61 is (None, 26, 26, 512)
            x, x_skip = x
            
#            x = DarknetConv(self.filters, 1)(x)
            x = UpSampling2D(2)(x) # increase the spatial size
            x = self.yolo_conv_prev(x) # Concatenate feature map
            x = Concatenate()([x, x_skip])
            print("Concatenate shape:", x.shape)
        x = self.yolo_conv_1(x)
        x = self.yolo_conv_2(x) 
        x = self.yolo_conv_3(x)
        x = self.yolo_conv_4(x)
        x = self.yolo_conv_5(x)
        
        return x

class YoloOutput(Model):
    """Initialize the Yolo detection layer after the 5th Yolo convolution layer
       before the final Yolo convolution layer.
    
    Args:
        Layer: Subclassing from Keras Model
        
    Returns:
        Tensor: Returns a tensors of shape (batch_size, grid, grid, featuremaps)
    """ 
    def __init__(self, filters, anchors, classes, name=''):
        super().__init__(name=name)
        self.filters = filters
        self.anchors = anchors
        self.classes = classes
        
        self.yolo_conv_6 = DarknetConv(filters=self.filters * 2, kernel_size=3, strides=1, name='yolo_conv_6')
        self.yolo_detections = DarknetConv(filters=anchors * (classes + 5), kernel_size=1, strides=1, batch_norm=False, name='yolo_detections')
        
    def call(self, x):
        print('yolo_output_shape_pre', x.shape)
        x = self.yolo_conv_6(x) # YoloV3 6th layer before detection layer
        x = self.yolo_detections(x) # YoloV3 detection layer 
        # x.shape -> (1, 13, 13, 75) where 75 = 3 * (20 + 5)
        x = tf.reshape(x, (-1, tf.shape(x)[1], tf.shape(x)[2], self.anchors, self.classes + 5))
        print('yolo_output_shape', x.shape)
        return x

#darknet = Darknet()
#_ = darknet(tf.ones([1, 416, 416, 3]))                      

class YoloV3(Model):
    """Initialize the YoloV3 architecture
    
    Args:
        Layer: Subclassing from Keras Model
        
    Returns:
        Tensor: Returns a tensors of shape (batch_size, grid, grid, featuremaps)
    """ 
    def __init__(self, anchors=anchors, masks=anchor_masks,
                 classes=1, training=False):
        super().__init__('yolov3')
        self.anchors = anchors
        self.masks = masks
        self.classes = classes    
        
    def build(self, input_shape):
        # Initialize the Darknet feature extractor
        self.darknet = Darknet(name='darknet53') 
        
        # Initialize the yolo convolution block for the large scale
        self.yolo_conv_1 = YoloConv(512, name='yolo_conv_blk_large')
        self.yolo_output_1 = YoloOutput(512, len(self.masks[0]), self.classes, name='yolo_detections_large')
        
        # Initialize the yolo convolution block for the medum scale        
        self.yolo_conv_2 = YoloConv(256, isConcat=True, name='yolo_conv_blk_medium')
        self.yolo_output_2 = YoloOutput(256, len(self.masks[1]), self.classes, name='yolo_detections_medium')
        
        # Initialize the yolo convolution block for the small scale
        self.yolo_conv_3 = YoloConv(128, isConcat=True, name='yolo_conv_blk_small')
        self.yolo_output_3 = YoloOutput(128, len(self.masks[2]), self.classes, name='yolo_detections_small')
            
        super().build(input_shape)
        
    def call(self, x): # Forward propagation function
        """
        Important:
            Need to determine the input shape of the first layer before the chain
            can be propagated to the future layers
        """
        
#        x = inputs = Input(x.shape[1:]) # (416, 416, 3) Don't pass in batch_size
#        print(inputs)
#        x = inputs = Input([416, 416, 3])
#        inputs = Input([416,416,3])

        inputs, x_36, x_61, x = self.darknet(x)
        
        x = self.yolo_conv_1(x)
        output_large = self.yolo_output_1(x)
        
        x = self.yolo_conv_2((x, x_61))
        output_medium = self.yolo_output_2(x)
        
        x = self.yolo_conv_3((x, x_36))
        output_small = self.yolo_output_3(x)
        
        
#        if training:
#            return Model(..)
        
        """
        Preprocessing of all the predicted boxes at three scales
            boxes_large: 13 x 13 layer for detecting large objects
            boxes_medium: 26 x 26 layer for detecting medium objects
            boxes_small: 52 x 52 layer for detection small objects
        """
        boxes_large = getFinalYoloBoxes(output_large, self.anchors[self.masks[0]], self.classes)
        boxes_medium = getFinalYoloBoxes(output_medium, self.anchors[self.masks[1]], self.classes)
        boxes_small = getFinalYoloBoxes(output_small, self.anchors[self.masks[2]], self.classes)

        boxes_all = (boxes_large[:3], boxes_medium[:3], boxes_small[:3])
        
        # Perform non-max-suppresion on the boxes to remove boxes with low confidences
        outputs = yolo_nms(boxes_all, self.classes)        
        
#        boxes, scores, classes, nums = yolo(tf.ones([1, 416, 416, 3]))
        return outputs
    
    
    def model(self, input_shape): # provided input shape
        x = Input(shape=(input_shape))
        return Model(inputs=[x], outputs=self.call(x))

"""
START debugging
    inspecting of outputs printed by each layers, sublayers and model.
"""
#yolov3_list = darknet_list + flatten_tensors_list
#darknet_conv_0 = yolo.get_layer('darknet53').layers[0].conv
#weights_file = "./lock_only_top_view_default_1900.weights"
#output_path = "./yolov3_.tf"
#load_darknet_weights(yolov3_list, weights_file)
#yolo.save_weights(output_path)

# To initialize the model, so layers get executed with weights
# yolo.model((416,416,3)).layers



#darknet = Darknet()
#darknet.build((1,416,416,3))
#model = darknet
#model = yolo
        
    
#x = tf.ones([1, 416, 416, 3])
#darknet = Darknet()
##_ = darknet(tf.ones([1, 416, 416, 3]))
#_ = darknet(x)


#inputx, x_36, x_61, x = Darknet()(x)
#
#x_large = YoloConv(512) # (1, 13, 13, 512), 5th layer of yolo_conv
#_ = x_large(x)
#output_large = YoloOutput(512, 3, 80)
#_ = output_large(x) # (1, 13, 13, 3, 25), yolo output layer

#x = YoloConv(256)((x, x_61))
#output_medium = YoloOutput(256, 3, 80)(x) # (1, 26, 26, 3, 25)
#
#x = YoloConv(128)((x, x_36)) # (1, 52, 52, 25)
#output_small = YoloOutput(128, 3, 80)(x)
"""
END debugging:
"""




